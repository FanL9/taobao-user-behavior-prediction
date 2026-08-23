"""Build and validate the initial stage-two user-item feature table."""

from __future__ import annotations

import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FEATURE_DIRECTORY = PROJECT_ROOT / "data" / "features"
DEFAULT_OUTPUT = DEFAULT_FEATURE_DIRECTORY / "user_item_feature_table.parquet"

INPUT_FILENAMES = {
    "user_item": "user_item_features.parquet",
    "user": "user_features.parquet",
    "sequence": "user_sequence_features.parquet",
    "item": "item_features.parquet",
    "category": "category_features.parquet",
    "time": "time_features.parquet",
    "conversion": "item_conversion_features.parquet",
}


@dataclass(frozen=True)
class FeatureTableBuildResult:
    output_path: Path
    rows: int
    columns: int
    elapsed_seconds: float
    validation: dict[str, object]


def _validate_unique_key(table: pa.Table, keys: list[str], name: str) -> None:
    if any(table[key].null_count for key in keys):
        raise RuntimeError(f"{name} contains a null join key")
    grouped = table.group_by(keys).aggregate([([], "count_all")])
    if grouped.num_rows != table.num_rows:
        raise RuntimeError(f"{name} join key is not unique: {keys}")


def _sequence_for_join(sequence: pa.Table) -> pa.Table:
    encoded = pa.array(
        [
            "|".join(str(int(value)) for value in values)
            for values in sequence["sequence_recent_10_behavior_types"].to_pylist()
        ],
        type=pa.string(),
    )
    index = sequence.schema.get_field_index("sequence_recent_10_behavior_types")
    return sequence.set_column(index, "sequence_recent_10_behavior_types", encoded)


def _left_join(
    left: pa.Table,
    right: pa.Table,
    *,
    keys: list[str],
    name: str,
    right_keys: list[str] | None = None,
) -> pa.Table:
    before = left.num_rows
    joined = left.join(
        right,
        keys=keys,
        right_keys=right_keys,
        join_type="left outer",
        use_threads=True,
    )
    if joined.num_rows != before:
        raise RuntimeError(f"{name} join changed row count from {before} to {joined.num_rows}")
    return joined


def _all_true(values: pa.Array | pa.ChunkedArray) -> bool:
    result = pc.all(values).as_py()
    return bool(result) if result is not None else False


def validate_feature_table(table: pa.Table) -> dict[str, object]:
    required = {
        "user_id",
        "item_id",
        "category_id",
        "ui_last_interaction_time",
        "user_total_count",
        "sequence_recent_10_behavior_types",
        "item_total_count",
        "item_popularity_level",
        "category_total_count",
        "category_popularity_level",
        "time_total_count",
        "time_is_peak_hour",
        "conversion_pv_to_buy_rate",
        "conversion_has_full_funnel",
    }
    missing = sorted(required - set(table.column_names))
    if missing:
        raise RuntimeError(f"Feature table is missing required fields: {missing}")
    if table.num_rows == 0:
        raise RuntimeError("Feature table is empty")
    if any(column.null_count for column in table.columns):
        null_columns = [
            name for name in table.column_names if table[name].null_count
        ]
        raise RuntimeError(f"Feature table contains null values: {null_columns}")

    _validate_unique_key(table, ["user_id", "item_id"], "feature table")

    count_columns = [
        name
        for name in table.column_names
        if name.endswith("_count") and pa.types.is_integer(table[name].type)
    ]
    negative_counts = sum(
        int(pc.sum(pc.cast(pc.less(table[name], 0), pa.int64())).as_py())
        for name in count_columns
    )
    if negative_counts:
        raise RuntimeError("Feature table contains negative count features")

    rate_columns = [name for name in table.column_names if name.endswith("_rate")]
    invalid_rates = sum(
        int(
            pc.sum(
                pc.cast(
                    pc.or_(
                        pc.invert(pc.is_finite(table[name])),
                        pc.less(table[name], 0.0),
                    ),
                    pa.int64(),
                )
            ).as_py()
        )
        for name in rate_columns
    )
    if invalid_rates:
        raise RuntimeError("Feature table contains invalid rate features")

    binary_columns = [
        "user_is_buyer",
        "user_is_repeat_buyer",
        "is_weekend",
        "time_is_peak_hour",
        "sequence_has_pv_cart",
        "sequence_has_pv_fav",
        "sequence_has_pv_buy",
        "sequence_has_pv_cart_buy",
        "ui_has_bought",
        "conversion_has_full_funnel",
    ]
    for name in binary_columns:
        if not _all_true(pc.is_in(table[name], value_set=pa.array([0, 1], type=pa.uint8()))):
            raise RuntimeError(f"{name} contains values other than 0/1")

    for source, target in (
        ("item_pv_count", "conversion_pv_count"),
        ("item_fav_count", "conversion_fav_count"),
        ("item_cart_count", "conversion_cart_count"),
        ("item_buy_count", "conversion_buy_count"),
    ):
        if not _all_true(pc.equal(table[source], table[target])):
            raise RuntimeError(f"{source} and {target} are inconsistent")
    expected_bought = pc.cast(pc.greater(table["ui_buy_count"], 0), pa.uint8())
    if not _all_true(pc.equal(table["ui_has_bought"], expected_bought)):
        raise RuntimeError("ui_has_bought is inconsistent with ui_buy_count")
    if not _all_true(
        pc.equal(
            pc.cast(table["ui_last_interaction_time"], pa.date32()),
            table["ui_last_interaction_date"],
        )
    ):
        raise RuntimeError("Last interaction date is inconsistent")
    if not _all_true(
        pc.equal(
            pc.cast(pc.hour(table["ui_last_interaction_time"]), pa.uint8()),
            table["ui_last_interaction_hour"],
        )
    ):
        raise RuntimeError("Last interaction hour is inconsistent")

    allowed_categories = {
        "user_activity_level": ["high", "low"],
        "item_popularity_level": ["low", "medium", "high"],
        "category_popularity_level": ["long_tail", "medium", "popular"],
        "time_period": ["night", "morning", "afternoon", "evening"],
    }
    for name, allowed in allowed_categories.items():
        if not _all_true(pc.is_in(table[name], value_set=pa.array(allowed))):
            raise RuntimeError(f"{name} contains an invalid category")

    return {
        "status": "PASS",
        "rows": table.num_rows,
        "columns": table.num_columns,
        "duplicate_primary_key": 0,
        "null_value_count": 0,
        "negative_count_feature_count": 0,
        "invalid_rate_feature_count": 0,
        "member_output_consistency": "PASS",
    }


def build_stage2_feature_table(
    feature_directory: Path | str = DEFAULT_FEATURE_DIRECTORY,
    *,
    output_path: Path | str = DEFAULT_OUTPUT,
) -> FeatureTableBuildResult:
    started_at = time.perf_counter()
    feature_directory = Path(feature_directory).resolve()
    output_path = Path(output_path).resolve()
    paths = {
        name: feature_directory / filename for name, filename in INPUT_FILENAMES.items()
    }
    missing_paths = [str(path) for path in paths.values() if not path.is_file()]
    if missing_paths:
        raise FileNotFoundError(f"Missing feature table inputs: {missing_paths}")

    tables = {name: pq.read_table(path) for name, path in paths.items()}
    _validate_unique_key(tables["user_item"], ["user_id", "item_id"], "user-item")
    _validate_unique_key(tables["user"], ["user_id"], "user")
    _validate_unique_key(tables["sequence"], ["user_id"], "sequence")
    _validate_unique_key(tables["item"], ["item_id"], "item")
    _validate_unique_key(tables["category"], ["category_id"], "category")
    _validate_unique_key(tables["time"], ["behavior_date", "behavior_hour"], "time")
    _validate_unique_key(tables["conversion"], ["item_id"], "conversion")

    wide = tables["user_item"]
    wide = _left_join(wide, tables["user"], keys=["user_id"], name="user")
    wide = _left_join(
        wide,
        _sequence_for_join(tables["sequence"]),
        keys=["user_id"],
        name="sequence",
    )
    wide = _left_join(wide, tables["item"], keys=["item_id"], name="item")
    wide = _left_join(wide, tables["category"], keys=["category_id"], name="category")
    wide = _left_join(
        wide,
        tables["time"],
        keys=["ui_last_interaction_date", "ui_last_interaction_hour"],
        right_keys=["behavior_date", "behavior_hour"],
        name="time",
    )
    wide = _left_join(
        wide, tables["conversion"], keys=["item_id"], name="conversion"
    )

    validation = validate_feature_table(wide)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        prefix=f".{output_path.stem}.",
        suffix=".parquet.tmp",
        dir=output_path.parent,
        delete=False,
    )
    handle.close()
    temporary = Path(handle.name)
    try:
        pq.write_table(
            wide,
            temporary,
            compression="snappy",
            row_group_size=100_000,
            use_dictionary=True,
        )
        metadata = pq.ParquetFile(temporary).metadata
        if metadata.num_rows != wide.num_rows:
            raise RuntimeError("Written feature table row count is inconsistent")
        temporary.replace(output_path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise

    return FeatureTableBuildResult(
        output_path=output_path,
        rows=wide.num_rows,
        columns=wide.num_columns,
        elapsed_seconds=round(time.perf_counter() - started_at, 3),
        validation=validation,
    )
