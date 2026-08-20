"""Build the four stage-two intermediate feature tables from clean Parquet."""

from __future__ import annotations

import gc
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PARQUET_INPUT = (
    PROJECT_ROOT / "data" / "processed" / "user_behavior_clean.parquet"
)
OBSERVATION_START = datetime(2025, 11, 18, 0, 0, 0)
OBSERVATION_END = datetime(2025, 12, 18, 23, 0, 0)
RECENCY_REFERENCE_TIME = datetime(2025, 12, 19, 0, 0, 0)
BEHAVIOR_MAPPING = {1: "pv", 2: "fav", 3: "cart", 4: "buy"}
REQUIRED_INPUT_COLUMNS = (
    "time",
    "user_id",
    "item_id",
    "category_id",
    "behavior_type",
    "behavior_name",
    "behavior_date",
    "behavior_hour",
    "weekday",
)
INPUT_COLUMNS = (
    "time",
    "user_id",
    "item_id",
    "category_id",
    "behavior_type",
    "behavior_date",
    "behavior_hour",
    "weekday",
)
HOURS_IN_NANOSECOND = 3_600_000_000_000.0
OUTPUT_SCHEMAS = {
    "user_features": pa.schema(
        [
            ("user_id", pa.int64()),
            ("user_total_count", pa.int64()),
            ("user_pv_count", pa.int64()),
            ("user_fav_count", pa.int64()),
            ("user_cart_count", pa.int64()),
            ("user_buy_count", pa.int64()),
            ("user_unique_item_count", pa.int64()),
            ("user_unique_category_count", pa.int64()),
            ("user_active_day_count", pa.int32()),
            ("user_first_behavior_time", pa.timestamp("ns")),
            ("user_last_behavior_time", pa.timestamp("ns")),
            ("user_recency_hours", pa.float64()),
            ("user_fav_to_pv_rate", pa.float64()),
            ("user_cart_to_pv_rate", pa.float64()),
            ("user_buy_to_pv_rate", pa.float64()),
            ("user_is_buyer", pa.uint8()),
            ("user_is_repeat_buyer", pa.uint8()),
        ]
    ),
    "item_features": pa.schema(
        [
            ("item_id", pa.int64()),
            ("category_id", pa.int64()),
            ("item_total_count", pa.int64()),
            ("item_pv_count", pa.int64()),
            ("item_fav_count", pa.int64()),
            ("item_cart_count", pa.int64()),
            ("item_buy_count", pa.int64()),
            ("item_unique_user_count", pa.int64()),
            ("item_unique_buyer_count", pa.int64()),
            ("item_active_day_count", pa.int32()),
            ("item_fav_to_pv_rate", pa.float64()),
            ("item_cart_to_pv_rate", pa.float64()),
            ("item_buy_to_pv_rate", pa.float64()),
        ]
    ),
    "category_features": pa.schema(
        [
            ("category_id", pa.int64()),
            ("category_total_count", pa.int64()),
            ("category_pv_count", pa.int64()),
            ("category_fav_count", pa.int64()),
            ("category_cart_count", pa.int64()),
            ("category_buy_count", pa.int64()),
            ("category_unique_user_count", pa.int64()),
            ("category_unique_item_count", pa.int64()),
            ("category_unique_buyer_count", pa.int64()),
            ("category_fav_to_pv_rate", pa.float64()),
            ("category_cart_to_pv_rate", pa.float64()),
            ("category_buy_to_pv_rate", pa.float64()),
        ]
    ),
    "time_features": pa.schema(
        [
            ("behavior_date", pa.date32()),
            ("behavior_hour", pa.uint8()),
            ("weekday", pa.uint8()),
            ("time_total_count", pa.int64()),
            ("time_pv_count", pa.int64()),
            ("time_fav_count", pa.int64()),
            ("time_cart_count", pa.int64()),
            ("time_buy_count", pa.int64()),
            ("time_unique_user_count", pa.int64()),
            ("time_unique_item_count", pa.int64()),
            ("time_buy_to_pv_rate", pa.float64()),
        ]
    ),
}
TABLE_PRIMARY_KEYS = {
    "user_features": ("user_id",),
    "item_features": ("item_id",),
    "category_features": ("category_id",),
    "time_features": ("behavior_date", "behavior_hour"),
}
OUTPUT_FILENAMES = {
    name: f"{name}.parquet" for name in OUTPUT_SCHEMAS
}


@dataclass(frozen=True)
class IntermediateTableBuildResult:
    input_path: Path
    input_rows: int
    output_paths: dict[str, Path]
    output_rows: dict[str, int]
    elapsed_seconds: float


def _output_columns(name: str) -> list[str]:
    return OUTPUT_SCHEMAS[name].names


def _append_behavior_flags(table: pa.Table) -> pa.Table:
    behavior_type = table["behavior_type"]
    for value, name in BEHAVIOR_MAPPING.items():
        flag = pc.cast(
            pc.equal(behavior_type, pa.scalar(value, type=behavior_type.type)),
            pa.int64(),
        )
        table = table.append_column(f"_{name}_flag", flag)
    buyer_user_id = pc.if_else(
        pc.equal(behavior_type, pa.scalar(4, type=behavior_type.type)),
        table["user_id"],
        pa.scalar(None, type=table["user_id"].type),
    )
    return table.append_column("_buyer_user_id", buyer_user_id)


def _safe_rate(numerator: pa.ChunkedArray, denominator: pa.ChunkedArray) -> pa.Array:
    numerator_float = pc.cast(numerator, pa.float64())
    denominator_float = pc.cast(denominator, pa.float64())
    return pc.if_else(
        pc.greater(denominator_float, 0.0),
        pc.divide(numerator_float, denominator_float),
        pa.scalar(0.0, type=pa.float64()),
    )


def _rename(table: pa.Table, names: Iterable[str]) -> pa.Table:
    return table.rename_columns(list(names))


def _sort(table: pa.Table, keys: Iterable[str]) -> pa.Table:
    return table.sort_by([(key, "ascending") for key in keys])


def _date32(values: pa.ChunkedArray) -> pa.Array | pa.ChunkedArray:
    if pa.types.is_date32(values.type):
        return values
    if pa.types.is_timestamp(values.type):
        return pc.cast(values, pa.date32())
    parsed = pc.strptime(values, format="%Y-%m-%d", unit="s", error_is_null=False)
    return pc.cast(parsed, pa.date32())


def _recency_hours(last_times: pa.ChunkedArray) -> pa.Array:
    epoch = datetime(1970, 1, 1)
    reference_ns = int(
        (RECENCY_REFERENCE_TIME - epoch).total_seconds()
        * 1_000_000_000
    )
    delta_ns = pc.subtract(
        pa.scalar(reference_ns, type=pa.int64()),
        pc.cast(last_times, pa.int64()),
    )
    return pc.divide(
        pc.cast(delta_ns, pa.float64()),
        pa.scalar(HOURS_IN_NANOSECOND, type=pa.float64()),
    )


def build_user_features(clean: pa.Table) -> pa.Table:
    grouped = clean.group_by("user_id").aggregate(
        [
            ([], "count_all"),
            ("_pv_flag", "sum"),
            ("_fav_flag", "sum"),
            ("_cart_flag", "sum"),
            ("_buy_flag", "sum"),
            ("item_id", "count_distinct"),
            ("category_id", "count_distinct"),
            ("behavior_date", "count_distinct"),
            ("time", "min"),
            ("time", "max"),
        ]
    )
    grouped = _rename(
        grouped,
        [
            "user_id",
            "user_total_count",
            "user_pv_count",
            "user_fav_count",
            "user_cart_count",
            "user_buy_count",
            "user_unique_item_count",
            "user_unique_category_count",
            "user_active_day_count",
            "user_first_behavior_time",
            "user_last_behavior_time",
        ],
    )
    grouped = grouped.set_column(
        grouped.schema.get_field_index("user_active_day_count"),
        "user_active_day_count",
        pc.cast(grouped["user_active_day_count"], pa.int32()),
    )
    grouped = grouped.append_column(
        "user_recency_hours", _recency_hours(grouped["user_last_behavior_time"])
    )
    grouped = grouped.append_column(
        "user_fav_to_pv_rate",
        _safe_rate(grouped["user_fav_count"], grouped["user_pv_count"]),
    )
    grouped = grouped.append_column(
        "user_cart_to_pv_rate",
        _safe_rate(grouped["user_cart_count"], grouped["user_pv_count"]),
    )
    grouped = grouped.append_column(
        "user_buy_to_pv_rate",
        _safe_rate(grouped["user_buy_count"], grouped["user_pv_count"]),
    )
    grouped = grouped.append_column(
        "user_is_buyer",
        pc.cast(pc.greater_equal(grouped["user_buy_count"], 1), pa.uint8()),
    )
    grouped = grouped.append_column(
        "user_is_repeat_buyer",
        pc.cast(pc.greater_equal(grouped["user_buy_count"], 2), pa.uint8()),
    )
    return _sort(grouped.select(_output_columns("user_features")), ["user_id"])


def _canonical_item_categories(clean: pa.Table) -> pa.Table:
    counts = clean.group_by(["item_id", "category_id"]).aggregate(
        [([], "count_all")]
    )
    counts = counts.sort_by(
        [
            ("item_id", "ascending"),
            ("count_all", "descending"),
            ("category_id", "ascending"),
        ]
    )
    counts = counts.combine_chunks()
    item_ids = counts["item_id"].chunk(0)
    first_for_item = pc.fill_null(
        pc.not_equal(pc.pairwise_diff(item_ids), 0),
        True,
    )
    return counts.filter(first_for_item).select(["item_id", "category_id"])


def build_item_features(clean: pa.Table) -> pa.Table:
    canonical_categories = _canonical_item_categories(clean)
    grouped = clean.group_by("item_id").aggregate(
        [
            ([], "count_all"),
            ("_pv_flag", "sum"),
            ("_fav_flag", "sum"),
            ("_cart_flag", "sum"),
            ("_buy_flag", "sum"),
            ("user_id", "count_distinct"),
            ("_buyer_user_id", "count_distinct"),
            ("behavior_date", "count_distinct"),
        ]
    )
    grouped = _rename(
        grouped,
        [
            "item_id",
            "item_total_count",
            "item_pv_count",
            "item_fav_count",
            "item_cart_count",
            "item_buy_count",
            "item_unique_user_count",
            "item_unique_buyer_count",
            "item_active_day_count",
        ],
    )
    grouped = grouped.set_column(
        grouped.schema.get_field_index("item_active_day_count"),
        "item_active_day_count",
        pc.cast(grouped["item_active_day_count"], pa.int32()),
    )
    grouped = grouped.join(
        canonical_categories,
        keys="item_id",
        join_type="left outer",
    )
    grouped = grouped.append_column(
        "item_fav_to_pv_rate",
        _safe_rate(grouped["item_fav_count"], grouped["item_pv_count"]),
    )
    grouped = grouped.append_column(
        "item_cart_to_pv_rate",
        _safe_rate(grouped["item_cart_count"], grouped["item_pv_count"]),
    )
    grouped = grouped.append_column(
        "item_buy_to_pv_rate",
        _safe_rate(grouped["item_buy_count"], grouped["item_pv_count"]),
    )
    return _sort(grouped.select(_output_columns("item_features")), ["item_id"])


def build_category_features(clean: pa.Table) -> pa.Table:
    grouped = clean.group_by("category_id").aggregate(
        [
            ([], "count_all"),
            ("_pv_flag", "sum"),
            ("_fav_flag", "sum"),
            ("_cart_flag", "sum"),
            ("_buy_flag", "sum"),
            ("user_id", "count_distinct"),
            ("item_id", "count_distinct"),
            ("_buyer_user_id", "count_distinct"),
        ]
    )
    grouped = _rename(
        grouped,
        [
            "category_id",
            "category_total_count",
            "category_pv_count",
            "category_fav_count",
            "category_cart_count",
            "category_buy_count",
            "category_unique_user_count",
            "category_unique_item_count",
            "category_unique_buyer_count",
        ],
    )
    grouped = grouped.append_column(
        "category_fav_to_pv_rate",
        _safe_rate(grouped["category_fav_count"], grouped["category_pv_count"]),
    )
    grouped = grouped.append_column(
        "category_cart_to_pv_rate",
        _safe_rate(grouped["category_cart_count"], grouped["category_pv_count"]),
    )
    grouped = grouped.append_column(
        "category_buy_to_pv_rate",
        _safe_rate(grouped["category_buy_count"], grouped["category_pv_count"]),
    )
    return _sort(
        grouped.select(_output_columns("category_features")), ["category_id"]
    )


def build_time_features(clean: pa.Table) -> pa.Table:
    grouped = clean.group_by(["behavior_date", "behavior_hour"]).aggregate(
        [
            ("weekday", "min"),
            ([], "count_all"),
            ("_pv_flag", "sum"),
            ("_fav_flag", "sum"),
            ("_cart_flag", "sum"),
            ("_buy_flag", "sum"),
            ("user_id", "count_distinct"),
            ("item_id", "count_distinct"),
        ]
    )
    grouped = _rename(
        grouped,
        [
            "behavior_date",
            "behavior_hour",
            "weekday",
            "time_total_count",
            "time_pv_count",
            "time_fav_count",
            "time_cart_count",
            "time_buy_count",
            "time_unique_user_count",
            "time_unique_item_count",
        ],
    )
    grouped = grouped.set_column(
        grouped.schema.get_field_index("behavior_date"),
        "behavior_date",
        _date32(grouped["behavior_date"]),
    )
    grouped = grouped.append_column(
        "time_buy_to_pv_rate",
        _safe_rate(grouped["time_buy_count"], grouped["time_pv_count"]),
    )
    return _sort(
        grouped.select(_output_columns("time_features")),
        ["behavior_date", "behavior_hour"],
    )


def _load_clean_table(input_path: Path) -> pa.Table:
    input_columns = pq.read_schema(input_path).names
    missing = [column for column in REQUIRED_INPUT_COLUMNS if column not in input_columns]
    if missing:
        raise ValueError(f"Clean Parquet is missing required columns: {missing}")
    table = pq.read_table(
        input_path,
        columns=list(INPUT_COLUMNS),
        filters=[
            ("time", ">=", OBSERVATION_START),
            ("time", "<=", OBSERVATION_END),
        ],
        use_threads=True,
    )
    if table.num_rows == 0:
        raise ValueError("No clean rows fall inside the configured feature window")
    behavior_values = set(table["behavior_type"].unique().to_pylist())
    if behavior_values - set(BEHAVIOR_MAPPING):
        raise ValueError(f"Unexpected behavior_type values: {behavior_values}")
    return _append_behavior_flags(table)


def _temporary_output_path(target: Path) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        prefix=f".{target.stem}.",
        suffix=".parquet.tmp",
        dir=target.parent,
        delete=False,
    )
    handle.close()
    return Path(handle.name)


def _validate_output(name: str, table: pa.Table, input_rows: int) -> None:
    expected_columns = _output_columns(name)
    if table.column_names != expected_columns:
        raise RuntimeError(
            f"{name} columns differ from the feature specification: "
            f"{table.column_names}"
        )
    for field in OUTPUT_SCHEMAS[name]:
        expected_type = field.type
        actual_type = table.schema.field(field.name).type
        if actual_type != expected_type:
            raise RuntimeError(
                f"{name}.{field.name} has type {actual_type}; "
                f"expected {expected_type}"
            )
    if table.num_rows == 0:
        raise RuntimeError(f"{name} is empty")
    primary_key = TABLE_PRIMARY_KEYS[name]
    if any(table[key].null_count for key in primary_key):
        raise RuntimeError(f"{name} contains a null primary key")
    key_groups = table.group_by(list(primary_key)).aggregate(
        [([], "count_all")]
    )
    if key_groups.num_rows != table.num_rows:
        raise RuntimeError(f"{name} primary key is not unique")
    total_column = {
        "user_features": "user_total_count",
        "item_features": "item_total_count",
        "category_features": "category_total_count",
        "time_features": "time_total_count",
    }[name]
    if pc.sum(table[total_column]).as_py() != input_rows:
        raise RuntimeError(f"{name} total count does not reconcile to input rows")


def build_stage2_intermediate_tables(
    input_path: Path | str = DEFAULT_PARQUET_INPUT,
    *,
    output_directory: Path | str = PROJECT_ROOT / "data" / "features",
) -> IntermediateTableBuildResult:
    """Build, validate, and atomically write the four feature tables."""

    started_at = time.perf_counter()
    input_path = Path(input_path).resolve()
    output_directory = Path(output_directory).resolve()
    if input_path.suffix.lower() != ".parquet":
        raise ValueError("Full intermediate-table construction requires Parquet input")
    if not input_path.is_file():
        raise FileNotFoundError(f"Clean Parquet not found: {input_path}")

    clean = _load_clean_table(input_path)
    input_rows = clean.num_rows
    builders = {
        "user_features": build_user_features,
        "item_features": build_item_features,
        "category_features": build_category_features,
        "time_features": build_time_features,
    }
    output_paths: dict[str, Path] = {}
    output_rows: dict[str, int] = {}
    temporary_paths: list[Path] = []
    try:
        for name, builder in builders.items():
            table = builder(clean)
            _validate_output(name, table, input_rows)
            target = output_directory / OUTPUT_FILENAMES[name]
            temporary = _temporary_output_path(target)
            temporary_paths.append(temporary)
            pq.write_table(
                table,
                temporary,
                compression="snappy",
                row_group_size=100_000,
                use_dictionary=True,
            )
            written = pq.read_table(temporary)
            _validate_output(name, written, input_rows)
            temporary.replace(target)
            temporary_paths.remove(temporary)
            output_paths[name] = target
            output_rows[name] = table.num_rows
            del table, written
            gc.collect()
    except Exception:
        for temporary in temporary_paths:
            temporary.unlink(missing_ok=True)
        raise
    finally:
        del clean
        gc.collect()

    return IntermediateTableBuildResult(
        input_path=input_path,
        input_rows=input_rows,
        output_paths=output_paths,
        output_rows=output_rows,
        elapsed_seconds=round(time.perf_counter() - started_at, 3),
    )
