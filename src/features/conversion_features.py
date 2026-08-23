"""Build item-level and global conversion features for stage two."""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT = PROJECT_ROOT / "data" / "features" / "item_features.parquet"
DEFAULT_ITEM_OUTPUT = (
    PROJECT_ROOT / "data" / "features" / "item_conversion_features.parquet"
)
DEFAULT_GLOBAL_OUTPUT = (
    PROJECT_ROOT / "data" / "features" / "conversion_features.parquet"
)

ITEM_CONVERSION_SCHEMA = pa.schema(
    [
        ("item_id", pa.int64()),
        ("conversion_pv_count", pa.int64()),
        ("conversion_fav_count", pa.int64()),
        ("conversion_cart_count", pa.int64()),
        ("conversion_buy_count", pa.int64()),
        ("conversion_pv_to_fav_rate", pa.float64()),
        ("conversion_pv_to_cart_rate", pa.float64()),
        ("conversion_pv_to_buy_rate", pa.float64()),
        ("conversion_fav_to_buy_rate", pa.float64()),
        ("conversion_cart_to_buy_rate", pa.float64()),
        ("conversion_has_full_funnel", pa.uint8()),
    ]
)

GLOBAL_CONVERSION_SCHEMA = pa.schema(
    [
        ("conversion_scope", pa.string()),
        ("item_count", pa.int64()),
        ("full_funnel_item_count", pa.int64()),
        ("pv_count", pa.int64()),
        ("fav_count", pa.int64()),
        ("cart_count", pa.int64()),
        ("buy_count", pa.int64()),
        ("pv_to_fav_rate", pa.float64()),
        ("pv_to_cart_rate", pa.float64()),
        ("pv_to_buy_rate", pa.float64()),
        ("fav_to_buy_rate", pa.float64()),
        ("cart_to_buy_rate", pa.float64()),
    ]
)


@dataclass(frozen=True)
class ConversionBuildResult:
    input_path: Path
    item_output_path: Path
    global_output_path: Path
    item_rows: int
    global_rows: int


def _safe_rate(numerator: pa.ChunkedArray, denominator: pa.ChunkedArray) -> pa.Array:
    numerator_float = pc.cast(numerator, pa.float64())
    denominator_float = pc.cast(denominator, pa.float64())
    return pc.if_else(
        pc.greater(denominator_float, 0.0),
        pc.divide(numerator_float, denominator_float),
        pa.scalar(0.0, type=pa.float64()),
    )


def _scalar_rate(numerator: int, denominator: int) -> float:
    return 0.0 if denominator == 0 else numerator / denominator


def build_item_conversion_features(item_features: pa.Table) -> pa.Table:
    required = {
        "item_id",
        "item_pv_count",
        "item_fav_count",
        "item_cart_count",
        "item_buy_count",
    }
    missing = sorted(required - set(item_features.column_names))
    if missing:
        raise ValueError(f"Item features are missing required columns: {missing}")

    result = pa.table(
        {
            "item_id": item_features["item_id"],
            "conversion_pv_count": item_features["item_pv_count"],
            "conversion_fav_count": item_features["item_fav_count"],
            "conversion_cart_count": item_features["item_cart_count"],
            "conversion_buy_count": item_features["item_buy_count"],
        }
    )
    result = result.append_column(
        "conversion_pv_to_fav_rate",
        _safe_rate(result["conversion_fav_count"], result["conversion_pv_count"]),
    )
    result = result.append_column(
        "conversion_pv_to_cart_rate",
        _safe_rate(result["conversion_cart_count"], result["conversion_pv_count"]),
    )
    result = result.append_column(
        "conversion_pv_to_buy_rate",
        _safe_rate(result["conversion_buy_count"], result["conversion_pv_count"]),
    )
    result = result.append_column(
        "conversion_fav_to_buy_rate",
        _safe_rate(result["conversion_buy_count"], result["conversion_fav_count"]),
    )
    result = result.append_column(
        "conversion_cart_to_buy_rate",
        _safe_rate(result["conversion_buy_count"], result["conversion_cart_count"]),
    )
    has_full_funnel = pc.and_(
        pc.and_(
            pc.greater(result["conversion_pv_count"], 0),
            pc.greater(result["conversion_fav_count"], 0),
        ),
        pc.and_(
            pc.greater(result["conversion_cart_count"], 0),
            pc.greater(result["conversion_buy_count"], 0),
        ),
    )
    result = result.append_column(
        "conversion_has_full_funnel", pc.cast(has_full_funnel, pa.uint8())
    )
    return result.select(ITEM_CONVERSION_SCHEMA.names).sort_by(
        [("item_id", "ascending")]
    )


def build_global_conversion_features(item_conversion: pa.Table) -> pa.Table:
    totals = {
        name: int(pc.sum(item_conversion[f"conversion_{name}_count"]).as_py())
        for name in ("pv", "fav", "cart", "buy")
    }
    full_funnel_items = int(
        pc.sum(item_conversion["conversion_has_full_funnel"]).as_py()
    )
    return pa.table(
        {
            "conversion_scope": pa.array(["global"], type=pa.string()),
            "item_count": pa.array([item_conversion.num_rows], type=pa.int64()),
            "full_funnel_item_count": pa.array(
                [full_funnel_items], type=pa.int64()
            ),
            "pv_count": pa.array([totals["pv"]], type=pa.int64()),
            "fav_count": pa.array([totals["fav"]], type=pa.int64()),
            "cart_count": pa.array([totals["cart"]], type=pa.int64()),
            "buy_count": pa.array([totals["buy"]], type=pa.int64()),
            "pv_to_fav_rate": pa.array(
                [_scalar_rate(totals["fav"], totals["pv"])], type=pa.float64()
            ),
            "pv_to_cart_rate": pa.array(
                [_scalar_rate(totals["cart"], totals["pv"])], type=pa.float64()
            ),
            "pv_to_buy_rate": pa.array(
                [_scalar_rate(totals["buy"], totals["pv"])], type=pa.float64()
            ),
            "fav_to_buy_rate": pa.array(
                [_scalar_rate(totals["buy"], totals["fav"])], type=pa.float64()
            ),
            "cart_to_buy_rate": pa.array(
                [_scalar_rate(totals["buy"], totals["cart"])], type=pa.float64()
            ),
        },
        schema=GLOBAL_CONVERSION_SCHEMA,
    )


def _validate_item_conversion(table: pa.Table, item_features: pa.Table) -> None:
    if table.schema != ITEM_CONVERSION_SCHEMA:
        raise RuntimeError("Item conversion schema is invalid")
    if table.num_rows != item_features.num_rows:
        raise RuntimeError("Item conversion row count differs from item features")
    if table["item_id"].null_count:
        raise RuntimeError("Item conversion contains a null item_id")
    if table.group_by("item_id").aggregate([([], "count_all")]).num_rows != table.num_rows:
        raise RuntimeError("Item conversion item_id is not unique")
    for source, target in (
        ("item_pv_count", "conversion_pv_count"),
        ("item_fav_count", "conversion_fav_count"),
        ("item_cart_count", "conversion_cart_count"),
        ("item_buy_count", "conversion_buy_count"),
    ):
        if not pc.all(pc.equal(item_features[source], table[target])).as_py():
            raise RuntimeError(f"{target} differs from {source}")


def _atomic_write(table: pa.Table, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        prefix=f".{target.stem}.", suffix=".parquet.tmp", dir=target.parent, delete=False
    )
    handle.close()
    temporary = Path(handle.name)
    try:
        pq.write_table(
            table,
            temporary,
            compression="snappy",
            row_group_size=100_000,
            use_dictionary=True,
        )
        temporary.replace(target)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def build_conversion_features(
    input_path: Path | str = DEFAULT_INPUT,
    *,
    item_output_path: Path | str = DEFAULT_ITEM_OUTPUT,
    global_output_path: Path | str = DEFAULT_GLOBAL_OUTPUT,
) -> ConversionBuildResult:
    input_path = Path(input_path).resolve()
    item_output_path = Path(item_output_path).resolve()
    global_output_path = Path(global_output_path).resolve()
    if not input_path.is_file():
        raise FileNotFoundError(f"Item features not found: {input_path}")

    item_features = pq.read_table(input_path)
    item_conversion = build_item_conversion_features(item_features)
    global_conversion = build_global_conversion_features(item_conversion)
    _validate_item_conversion(item_conversion, item_features)
    if global_conversion.schema != GLOBAL_CONVERSION_SCHEMA:
        raise RuntimeError("Global conversion schema is invalid")

    _atomic_write(item_conversion, item_output_path)
    _atomic_write(global_conversion, global_output_path)
    return ConversionBuildResult(
        input_path=input_path,
        item_output_path=item_output_path,
        global_output_path=global_output_path,
        item_rows=item_conversion.num_rows,
        global_rows=global_conversion.num_rows,
    )


if __name__ == "__main__":
    result = build_conversion_features()
    print(f"created: {result.item_output_path} ({result.item_rows:,} rows)")
    print(f"created: {result.global_output_path} ({result.global_rows:,} row)")
