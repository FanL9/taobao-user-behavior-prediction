"""Stage-two feature definitions and intermediate-table schemas.

This module defines metadata only. It validates the clean input schema and can
export the feature dictionary and table schemas, but it does not aggregate the
full behavior dataset or build feature values.
"""

from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PARQUET_INPUT = (
    PROJECT_ROOT / "data" / "processed" / "user_behavior_clean.parquet"
)
DEFAULT_CSV_INPUT = (
    PROJECT_ROOT / "data" / "processed" / "user_behavior_clean.csv"
)
DEFAULT_DICTIONARY_OUTPUT = (
    PROJECT_ROOT / "data" / "features" / "stage2_feature_dictionary.csv"
)
DEFAULT_SCHEMA_OUTPUT = (
    PROJECT_ROOT
    / "data"
    / "features"
    / "stage2_intermediate_table_schemas.json"
)

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
BEHAVIOR_MAPPING = {1: "pv", 2: "fav", 3: "cart", 4: "buy"}


@dataclass(frozen=True)
class FeatureWindow:
    """Shared observation-window rules for all stage-two feature tables."""

    observation_start: datetime
    observation_end: datetime
    recency_reference_time: datetime
    time_granularity: str = "hour"
    timezone: str = "naive/source time"
    boundary_rule: str = "closed interval: start <= time <= end"


FEATURE_WINDOW = FeatureWindow(
    observation_start=datetime(2025, 11, 18, 0, 0, 0),
    observation_end=datetime(2025, 12, 18, 23, 0, 0),
    recency_reference_time=datetime(2025, 12, 18, 23, 0, 0)
    + timedelta(hours=1),
)

RATE_RULES = {
    "fav_to_pv_rate": "fav_count / pv_count",
    "cart_to_pv_rate": "cart_count / pv_count",
    "buy_to_pv_rate": "buy_count / pv_count",
    "zero_denominator": 0.0,
    "rounding": "retain full precision during calculation; round only for display",
}


@dataclass(frozen=True)
class FeatureDefinition:
    table_name: str
    feature_name: str
    data_type: str
    description: str
    calculation: str
    data_source: str
    granularity: str
    used_for_modeling: bool
    nullable: bool = False


@dataclass(frozen=True)
class TableDefinition:
    table_name: str
    output_path: str
    grain: str
    primary_key: tuple[str, ...]
    description: str


SOURCE_NAME = "data/processed/user_behavior_clean.parquet (CSV fallback)"


def _feature(
    table: str,
    name: str,
    dtype: str,
    description: str,
    calculation: str,
    grain: str,
    modeling: bool = True,
    *,
    nullable: bool = False,
) -> FeatureDefinition:
    return FeatureDefinition(
        table_name=table,
        feature_name=name,
        data_type=dtype,
        description=description,
        calculation=calculation,
        data_source=SOURCE_NAME,
        granularity=grain,
        used_for_modeling=modeling,
        nullable=nullable,
    )


TABLE_DEFINITIONS = (
    TableDefinition(
        table_name="user_features",
        output_path="data/features/user_features.parquet",
        grain="one row per user_id",
        primary_key=("user_id",),
        description="User activity, diversity, recency, and conversion features.",
    ),
    TableDefinition(
        table_name="item_features",
        output_path="data/features/item_features.parquet",
        grain="one row per item_id",
        primary_key=("item_id",),
        description="Item traffic, audience, and conversion features.",
    ),
    TableDefinition(
        table_name="category_features",
        output_path="data/features/category_features.parquet",
        grain="one row per category_id",
        primary_key=("category_id",),
        description="Category traffic, coverage, and conversion features.",
    ),
    TableDefinition(
        table_name="time_features",
        output_path="data/features/time_features.parquet",
        grain="one row per behavior_date and behavior_hour",
        primary_key=("behavior_date", "behavior_hour"),
        description="Hourly activity and conversion features for EDA and joins.",
    ),
)


FEATURE_DEFINITIONS = (
    # User table.
    _feature(
        "user_features", "user_id", "int64", "User identifier.",
        "grouping key: user_id", "user", False,
    ),
    _feature(
        "user_features", "user_total_count", "int64", "All user behaviors.",
        "count(*)", "user",
    ),
    _feature(
        "user_features", "user_pv_count", "int64", "User page-view count.",
        "sum(behavior_name = 'pv')", "user",
    ),
    _feature(
        "user_features", "user_fav_count", "int64", "User favorite count.",
        "sum(behavior_name = 'fav')", "user",
    ),
    _feature(
        "user_features", "user_cart_count", "int64", "User add-to-cart count.",
        "sum(behavior_name = 'cart')", "user",
    ),
    _feature(
        "user_features", "user_buy_count", "int64", "User purchase count.",
        "sum(behavior_name = 'buy')", "user",
    ),
    _feature(
        "user_features", "user_unique_item_count", "int64",
        "Distinct items interacted with by the user.", "nunique(item_id)", "user",
    ),
    _feature(
        "user_features", "user_unique_category_count", "int64",
        "Distinct categories interacted with by the user.",
        "nunique(category_id)", "user",
    ),
    _feature(
        "user_features", "user_active_day_count", "int32",
        "Distinct active dates for the user.", "nunique(behavior_date)", "user",
    ),
    _feature(
        "user_features", "user_first_behavior_time", "datetime64[ns]",
        "First observed behavior time.", "min(time)", "user", False,
    ),
    _feature(
        "user_features", "user_last_behavior_time", "datetime64[ns]",
        "Last observed behavior time.", "max(time)", "user", False,
    ),
    _feature(
        "user_features", "user_recency_hours", "float64",
        "Hours from the last behavior to the shared reference time.",
        "hours(recency_reference_time - max(time))", "user",
    ),
    _feature(
        "user_features", "user_fav_to_pv_rate", "float64",
        "Favorites per page view.",
        "user_fav_count / user_pv_count; 0 when denominator is 0", "user",
    ),
    _feature(
        "user_features", "user_cart_to_pv_rate", "float64",
        "Add-to-cart actions per page view.",
        "user_cart_count / user_pv_count; 0 when denominator is 0", "user",
    ),
    _feature(
        "user_features", "user_buy_to_pv_rate", "float64",
        "Purchases per page view.",
        "user_buy_count / user_pv_count; 0 when denominator is 0", "user",
    ),
    _feature(
        "user_features", "user_is_buyer", "uint8",
        "Whether the user has at least one purchase.",
        "1 if user_buy_count >= 1 else 0", "user",
    ),
    _feature(
        "user_features", "user_is_repeat_buyer", "uint8",
        "Whether the user has at least two purchase records.",
        "1 if user_buy_count >= 2 else 0", "user",
    ),

    # Item table.
    _feature(
        "item_features", "item_id", "int64", "Item identifier.",
        "grouping key: item_id", "item", False,
    ),
    _feature(
        "item_features", "category_id", "int64",
        "Canonical category of the item.",
        "most frequent category_id per item_id; smallest id breaks ties",
        "item",
    ),
    _feature(
        "item_features", "item_total_count", "int64", "All item behaviors.",
        "count(*)", "item",
    ),
    _feature(
        "item_features", "item_pv_count", "int64", "Item page-view count.",
        "sum(behavior_name = 'pv')", "item",
    ),
    _feature(
        "item_features", "item_fav_count", "int64", "Item favorite count.",
        "sum(behavior_name = 'fav')", "item",
    ),
    _feature(
        "item_features", "item_cart_count", "int64", "Item add-to-cart count.",
        "sum(behavior_name = 'cart')", "item",
    ),
    _feature(
        "item_features", "item_buy_count", "int64", "Item purchase count.",
        "sum(behavior_name = 'buy')", "item",
    ),
    _feature(
        "item_features", "item_unique_user_count", "int64",
        "Distinct users interacting with the item.", "nunique(user_id)", "item",
    ),
    _feature(
        "item_features", "item_unique_buyer_count", "int64",
        "Distinct users purchasing the item.",
        "nunique(user_id where behavior_name = 'buy')", "item",
    ),
    _feature(
        "item_features", "item_active_day_count", "int32",
        "Distinct dates on which the item had activity.",
        "nunique(behavior_date)", "item",
    ),
    _feature(
        "item_features", "item_fav_to_pv_rate", "float64",
        "Item favorites per page view.",
        "item_fav_count / item_pv_count; 0 when denominator is 0", "item",
    ),
    _feature(
        "item_features", "item_cart_to_pv_rate", "float64",
        "Item add-to-cart actions per page view.",
        "item_cart_count / item_pv_count; 0 when denominator is 0", "item",
    ),
    _feature(
        "item_features", "item_buy_to_pv_rate", "float64",
        "Item purchases per page view.",
        "item_buy_count / item_pv_count; 0 when denominator is 0", "item",
    ),

    # Category table.
    _feature(
        "category_features", "category_id", "int64", "Category identifier.",
        "grouping key: category_id", "category", False,
    ),
    _feature(
        "category_features", "category_total_count", "int64",
        "All category behaviors.", "count(*)", "category",
    ),
    _feature(
        "category_features", "category_pv_count", "int64",
        "Category page-view count.", "sum(behavior_name = 'pv')", "category",
    ),
    _feature(
        "category_features", "category_fav_count", "int64",
        "Category favorite count.", "sum(behavior_name = 'fav')", "category",
    ),
    _feature(
        "category_features", "category_cart_count", "int64",
        "Category add-to-cart count.",
        "sum(behavior_name = 'cart')", "category",
    ),
    _feature(
        "category_features", "category_buy_count", "int64",
        "Category purchase count.", "sum(behavior_name = 'buy')", "category",
    ),
    _feature(
        "category_features", "category_unique_user_count", "int64",
        "Distinct users interacting with the category.",
        "nunique(user_id)", "category",
    ),
    _feature(
        "category_features", "category_unique_item_count", "int64",
        "Distinct items in the category.", "nunique(item_id)", "category",
    ),
    _feature(
        "category_features", "category_unique_buyer_count", "int64",
        "Distinct users purchasing in the category.",
        "nunique(user_id where behavior_name = 'buy')", "category",
    ),
    _feature(
        "category_features", "category_fav_to_pv_rate", "float64",
        "Category favorites per page view.",
        "category_fav_count / category_pv_count; 0 when denominator is 0",
        "category",
    ),
    _feature(
        "category_features", "category_cart_to_pv_rate", "float64",
        "Category add-to-cart actions per page view.",
        "category_cart_count / category_pv_count; 0 when denominator is 0",
        "category",
    ),
    _feature(
        "category_features", "category_buy_to_pv_rate", "float64",
        "Category purchases per page view.",
        "category_buy_count / category_pv_count; 0 when denominator is 0",
        "category",
    ),

    # Time table.
    _feature(
        "time_features", "behavior_date", "date32", "Calendar date.",
        "grouping key: behavior_date", "date-hour", False,
    ),
    _feature(
        "time_features", "behavior_hour", "uint8", "Hour of day, 0 through 23.",
        "grouping key: behavior_hour", "date-hour",
    ),
    _feature(
        "time_features", "weekday", "uint8", "Monday=0 through Sunday=6.",
        "unique weekday derived from behavior_date", "date-hour",
    ),
    _feature(
        "time_features", "time_total_count", "int64",
        "All behaviors during the date-hour.", "count(*)", "date-hour",
    ),
    _feature(
        "time_features", "time_pv_count", "int64",
        "Page views during the date-hour.",
        "sum(behavior_name = 'pv')", "date-hour",
    ),
    _feature(
        "time_features", "time_fav_count", "int64",
        "Favorites during the date-hour.",
        "sum(behavior_name = 'fav')", "date-hour",
    ),
    _feature(
        "time_features", "time_cart_count", "int64",
        "Add-to-cart actions during the date-hour.",
        "sum(behavior_name = 'cart')", "date-hour",
    ),
    _feature(
        "time_features", "time_buy_count", "int64",
        "Purchases during the date-hour.",
        "sum(behavior_name = 'buy')", "date-hour",
    ),
    _feature(
        "time_features", "time_unique_user_count", "int64",
        "Distinct active users during the date-hour.",
        "nunique(user_id)", "date-hour",
    ),
    _feature(
        "time_features", "time_unique_item_count", "int64",
        "Distinct active items during the date-hour.",
        "nunique(item_id)", "date-hour",
    ),
    _feature(
        "time_features", "time_buy_to_pv_rate", "float64",
        "Purchases per page view during the date-hour.",
        "time_buy_count / time_pv_count; 0 when denominator is 0", "date-hour",
    ),
)


def resolve_clean_input(input_path: Path | str | None = None) -> Path:
    """Resolve an explicit input or prefer Parquet with a CSV fallback."""

    if input_path is not None:
        resolved = Path(input_path).resolve()
        if not resolved.is_file():
            raise FileNotFoundError(f"Clean input not found: {resolved}")
        return resolved
    for candidate in (DEFAULT_PARQUET_INPUT, DEFAULT_CSV_INPUT):
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(
        "No clean input found. Expected "
        f"{DEFAULT_PARQUET_INPUT} or {DEFAULT_CSV_INPUT}."
    )


def read_input_columns(input_path: Path | str) -> tuple[str, ...]:
    """Read only the input schema/header; no behavior rows are aggregated."""

    path = Path(input_path)
    suffix = path.suffix.lower()
    if suffix == ".parquet":
        return tuple(pq.read_schema(path).names)
    if suffix == ".csv":
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            header = next(csv.reader(handle), None)
        if header is None:
            raise ValueError(f"CSV is empty: {path}")
        return tuple(header)
    raise ValueError(f"Unsupported clean input format: {path.suffix}")


def validate_clean_input_schema(input_path: Path | str) -> tuple[str, ...]:
    """Require the stage-one clean columns used by the feature definitions."""

    columns = read_input_columns(input_path)
    missing = [column for column in REQUIRED_INPUT_COLUMNS if column not in columns]
    if missing:
        raise ValueError(f"Clean input is missing required columns: {missing}")
    return columns


def _validate_specifications() -> None:
    tables = {table.table_name: table for table in TABLE_DEFINITIONS}
    if len(tables) != len(TABLE_DEFINITIONS):
        raise ValueError("Intermediate table names must be unique")

    fields_by_table: dict[str, set[str]] = {name: set() for name in tables}
    for feature in FEATURE_DEFINITIONS:
        if feature.table_name not in tables:
            raise ValueError(f"Unknown feature table: {feature.table_name}")
        fields = fields_by_table[feature.table_name]
        if feature.feature_name in fields:
            raise ValueError(
                f"Duplicate field {feature.table_name}.{feature.feature_name}"
            )
        fields.add(feature.feature_name)

    for table in TABLE_DEFINITIONS:
        missing_keys = set(table.primary_key) - fields_by_table[table.table_name]
        if missing_keys:
            raise ValueError(
                f"{table.table_name} is missing primary-key fields: {missing_keys}"
            )


def specification_payload() -> dict[str, Any]:
    """Return a JSON-serializable specification for all intermediate tables."""

    _validate_specifications()
    fields_by_table = {
        table.table_name: [
            asdict(feature)
            for feature in FEATURE_DEFINITIONS
            if feature.table_name == table.table_name
        ]
        for table in TABLE_DEFINITIONS
    }
    return {
        "schema_version": 1,
        "input_candidates": [
            "data/processed/user_behavior_clean.parquet",
            "data/processed/user_behavior_clean.csv",
        ],
        "required_input_columns": list(REQUIRED_INPUT_COLUMNS),
        "feature_window": {
            key: value.isoformat(sep=" ") if isinstance(value, datetime) else value
            for key, value in asdict(FEATURE_WINDOW).items()
        },
        "behavior_mapping": BEHAVIOR_MAPPING,
        "conversion_rate_rules": RATE_RULES,
        "tables": [
            {
                **asdict(table),
                "primary_key": list(table.primary_key),
                "fields": fields_by_table[table.table_name],
            }
            for table in TABLE_DEFINITIONS
        ],
    }


def export_feature_dictionary(
    output_path: Path | str = DEFAULT_DICTIONARY_OUTPUT,
) -> Path:
    """Write one feature-definition row per intermediate-table field."""

    _validate_specifications()
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(asdict(FEATURE_DEFINITIONS[0]).keys())
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(asdict(feature) for feature in FEATURE_DEFINITIONS)
    return path


def export_table_schemas(
    output_path: Path | str = DEFAULT_SCHEMA_OUTPUT,
) -> Path:
    """Write the shared rules and four intermediate-table schemas as JSON."""

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(specification_payload(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def export_stage2_specifications(
    *,
    input_path: Path | str | None = None,
    dictionary_output: Path | str = DEFAULT_DICTIONARY_OUTPUT,
    schema_output: Path | str = DEFAULT_SCHEMA_OUTPUT,
) -> tuple[Path, Path]:
    """Validate the clean schema and export both metadata deliverables."""

    clean_input = resolve_clean_input(input_path)
    validate_clean_input_schema(clean_input)
    dictionary_path = export_feature_dictionary(dictionary_output)
    schema_path = export_table_schemas(schema_output)
    return dictionary_path, schema_path

