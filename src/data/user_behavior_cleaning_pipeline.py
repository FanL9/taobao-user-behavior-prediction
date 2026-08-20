"""Chunked quality checks and cleaning for the user-behavior CSV.

Important duplicate policy
--------------------------
The source ``time`` field is only precise to the hour. Therefore repeated rows
with the same ``user_id + item_id + behavior_type + time`` cannot safely be
assumed to be accidental duplicates: a user may legitimately perform the same
behavior multiple times within that hour.

This pipeline preserves such repeated events by default. Only a suspicious
burst whose global count for the same four-field key reaches the configured
threshold (60 by default) is collapsed to one row. Because minute-level data is
not available, the threshold is applied within the source one-hour time bucket.
"""

from __future__ import annotations

import sqlite3
import tempfile
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq


EXPECTED_COLUMNS = [
    "time",
    "user_id",
    "item_id",
    "item_category",
    "behavior_type",
]
OUTPUT_COLUMNS = [
    "time",
    "user_id",
    "item_id",
    "category_id",
    "behavior_type",
    "behavior_name",
    "behavior_date",
    "behavior_hour",
    "weekday",
]
ID_COLUMNS = ("user_id", "item_id", "item_category")
BEHAVIOR_MAPPING = {1: "pv", 2: "fav", 3: "cart", 4: "buy"}
TIME_INPUT_FORMAT = "%Y-%m-%d %H"
TIME_OUTPUT_FORMAT = "%Y-%m-%d %H:%M:%S"
MAX_SQLITE_INTEGER = 2**63 - 1
DEFAULT_SUSPICIOUS_REPEAT_THRESHOLD = 60
PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class CleaningResult:
    """Paths and statistics returned by :func:`clean_user_behavior`."""

    csv_path: Path
    parquet_path: Path | None
    report_path: Path | None
    report: dict[str, Any]


@dataclass
class _ChunkAnalysis:
    stripped: pd.DataFrame
    missing_masks: pd.DataFrame
    missing_any: pd.Series
    parsed_ids: dict[str, pd.Series]
    valid_id_masks: dict[str, pd.Series]
    invalid_id_mask: pd.Series
    valid_behavior_mask: pd.Series
    invalid_behavior_mask: pd.Series
    parsed_time: pd.Series
    invalid_time_mask: pd.Series
    out_of_range_time_mask: pd.Series
    base_valid_mask: pd.Series


def _temporary_path(target: Path, suffix: str) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        prefix=f".{target.stem}.",
        suffix=suffix,
        dir=target.parent,
        delete=False,
    )
    handle.close()
    return Path(handle.name)


def _empty_clean_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "time": pd.Series(dtype="datetime64[ns]"),
            "user_id": pd.Series(dtype="int64"),
            "item_id": pd.Series(dtype="int64"),
            "category_id": pd.Series(dtype="int64"),
            "behavior_type": pd.Series(dtype="uint8"),
            "behavior_name": pd.Series(dtype="string"),
            "behavior_date": pd.Series(dtype="string"),
            "behavior_hour": pd.Series(dtype="uint8"),
            "weekday": pd.Series(dtype="uint8"),
        }
    )[OUTPUT_COLUMNS]


def _parse_identifier(values: pd.Series) -> tuple[pd.Series, pd.Series]:
    """Parse positive, signed-64-bit-compatible integer identifiers."""

    parsed = pd.Series(pd.NA, index=values.index, dtype="Int64")
    format_ok = values.str.fullmatch(r"[0-9]+", na=False)
    normalized = values.str.lstrip("0")
    max_value = str(MAX_SQLITE_INTEGER)
    within_int64 = (
        normalized.str.len().lt(len(max_value))
        | (
            normalized.str.len().eq(len(max_value))
            & normalized.le(max_value)
        )
    )
    valid = format_ok & normalized.ne("") & within_int64
    if valid.any():
        parsed.loc[valid] = pd.to_numeric(
            normalized.loc[valid],
            errors="raise",
        ).astype("int64")
    return parsed, parsed.notna()


def _parse_time(values: pd.Series) -> pd.Series:
    parsed = pd.Series(pd.NaT, index=values.index, dtype="datetime64[ns]")
    format_ok = values.str.fullmatch(
        r"[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}",
        na=False,
    )
    if format_ok.any():
        parsed.loc[format_ok] = pd.to_datetime(
            values.loc[format_ok],
            format=TIME_INPUT_FORMAT,
            errors="coerce",
            exact=True,
        )
    return parsed


def _parse_time_boundary(
    value: str | pd.Timestamp | None,
    *,
    name: str,
) -> pd.Timestamp | None:
    """Parse an optional inclusive time boundary using the input time format."""

    if value is None:
        return None

    if isinstance(value, pd.Timestamp):
        parsed = value
    else:
        parsed = pd.to_datetime(
            str(value),
            format=TIME_INPUT_FORMAT,
            errors="coerce",
            exact=True,
        )

    if pd.isna(parsed):
        raise ValueError(f"{name} must match {TIME_INPUT_FORMAT}; got {value!r}")
    return pd.Timestamp(parsed)


def _analyze_chunk(
    raw_chunk: pd.DataFrame,
    *,
    allowed_start: pd.Timestamp | None,
    allowed_end: pd.Timestamp | None,
) -> _ChunkAnalysis:
    stripped = raw_chunk.apply(lambda column: column.str.strip())
    missing_masks = stripped.eq("")
    missing_any = missing_masks.any(axis=1)

    parsed_ids: dict[str, pd.Series] = {}
    valid_id_masks: dict[str, pd.Series] = {}
    invalid_id_parts: list[pd.Series] = []
    for column in ID_COLUMNS:
        parsed_ids[column], valid_id_masks[column] = _parse_identifier(
            stripped[column]
        )
        invalid_id_parts.append(
            ~missing_masks[column] & ~valid_id_masks[column]
        )
    invalid_id_mask = pd.concat(invalid_id_parts, axis=1).any(axis=1)

    valid_behavior_mask = stripped["behavior_type"].isin(
        {str(value) for value in BEHAVIOR_MAPPING}
    )
    invalid_behavior_mask = (
        ~missing_masks["behavior_type"] & ~valid_behavior_mask
    )

    parsed_time = _parse_time(stripped["time"])
    invalid_time_mask = ~missing_masks["time"] & parsed_time.isna()

    out_of_range_time_mask = pd.Series(False, index=raw_chunk.index, dtype=bool)
    if allowed_start is not None:
        out_of_range_time_mask |= parsed_time.notna() & parsed_time.lt(allowed_start)
    if allowed_end is not None:
        out_of_range_time_mask |= parsed_time.notna() & parsed_time.gt(allowed_end)

    base_valid_mask = ~(
        missing_any
        | invalid_behavior_mask
        | invalid_id_mask
        | invalid_time_mask
        | out_of_range_time_mask
    )

    return _ChunkAnalysis(
        stripped=stripped,
        missing_masks=missing_masks,
        missing_any=missing_any,
        parsed_ids=parsed_ids,
        valid_id_masks=valid_id_masks,
        invalid_id_mask=invalid_id_mask,
        valid_behavior_mask=valid_behavior_mask,
        invalid_behavior_mask=invalid_behavior_mask,
        parsed_time=parsed_time,
        invalid_time_mask=invalid_time_mask,
        out_of_range_time_mask=out_of_range_time_mask,
        base_valid_mask=base_valid_mask,
    )


def _clean_frame_from_analysis(analysis: _ChunkAnalysis, mask: pd.Series) -> pd.DataFrame:
    clean_chunk = pd.DataFrame(
        {
            "time": analysis.parsed_time.loc[mask],
            "user_id": analysis.parsed_ids["user_id"].loc[mask].astype("int64"),
            "item_id": analysis.parsed_ids["item_id"].loc[mask].astype("int64"),
            "category_id": analysis.parsed_ids["item_category"]
            .loc[mask]
            .astype("int64"),
            "behavior_type": analysis.stripped.loc[mask, "behavior_type"].astype(
                "uint8"
            ),
        }
    )
    clean_chunk["behavior_name"] = clean_chunk["behavior_type"].map(
        BEHAVIOR_MAPPING
    ).astype("string")
    clean_chunk["behavior_date"] = clean_chunk["time"].dt.strftime(
        "%Y-%m-%d"
    ).astype("string")
    clean_chunk["behavior_hour"] = clean_chunk["time"].dt.hour.astype("uint8")
    clean_chunk["weekday"] = clean_chunk["time"].dt.weekday.astype("uint8")
    return clean_chunk[OUTPUT_COLUMNS]


def _repeat_keys_from_clean_chunk(clean_chunk: pd.DataFrame) -> list[tuple[int, int, int, str]]:
    if clean_chunk.empty:
        return []
    time_values = clean_chunk["time"].dt.strftime(TIME_OUTPUT_FORMAT)
    return [
        (int(user_id), int(item_id), int(behavior_type), time_value)
        for user_id, item_id, behavior_type, time_value in zip(
            clean_chunk["user_id"],
            clean_chunk["item_id"],
            clean_chunk["behavior_type"],
            time_values,
        )
    ]


class _DiskQualityTracker:
    """Disk-backed exact statistics across chunks, including repeat burst counts."""

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        self.connection = sqlite3.connect(database_path)
        self.connection.execute("PRAGMA journal_mode = OFF")
        self.connection.execute("PRAGMA synchronous = OFF")
        self.connection.execute("PRAGMA temp_store = MEMORY")
        self.connection.executescript(
            """
            CREATE TABLE raw_full_seen (
                time_value TEXT NOT NULL,
                user_id TEXT NOT NULL,
                item_id TEXT NOT NULL,
                item_category TEXT NOT NULL,
                behavior_type TEXT NOT NULL,
                PRIMARY KEY (
                    time_value,
                    user_id,
                    item_id,
                    item_category,
                    behavior_type
                )
            ) WITHOUT ROWID;

            CREATE TABLE raw_quad_seen (
                user_id TEXT NOT NULL,
                item_id TEXT NOT NULL,
                behavior_type TEXT NOT NULL,
                time_value TEXT NOT NULL,
                PRIMARY KEY (user_id, item_id, behavior_type, time_value)
            ) WITHOUT ROWID;

            CREATE TABLE repeat_counts (
                user_id INTEGER NOT NULL,
                item_id INTEGER NOT NULL,
                behavior_type INTEGER NOT NULL,
                time_value TEXT NOT NULL,
                count_value INTEGER NOT NULL,
                PRIMARY KEY (user_id, item_id, behavior_type, time_value)
            ) WITHOUT ROWID;
            """
        )

    def raw_duplicate_counts(self, chunk: pd.DataFrame) -> tuple[int, int]:
        before = self.connection.total_changes
        self.connection.executemany(
            """
            INSERT OR IGNORE INTO raw_full_seen
            (time_value, user_id, item_id, item_category, behavior_type)
            VALUES (?, ?, ?, ?, ?)
            """,
            chunk[EXPECTED_COLUMNS].itertuples(index=False, name=None),
        )
        full_inserted = self.connection.total_changes - before

        before = self.connection.total_changes
        self.connection.executemany(
            """
            INSERT OR IGNORE INTO raw_quad_seen
            (user_id, item_id, behavior_type, time_value)
            VALUES (?, ?, ?, ?)
            """,
            chunk[["user_id", "item_id", "behavior_type", "time"]].itertuples(
                index=False,
                name=None,
            ),
        )
        quad_inserted = self.connection.total_changes - before
        return len(chunk) - full_inserted, len(chunk) - quad_inserted

    def add_repeat_counts(self, clean_candidates: pd.DataFrame) -> None:
        rows = _repeat_keys_from_clean_chunk(clean_candidates)
        if not rows:
            return
        self.connection.executemany(
            """
            INSERT INTO repeat_counts
            (user_id, item_id, behavior_type, time_value, count_value)
            VALUES (?, ?, ?, ?, 1)
            ON CONFLICT(user_id, item_id, behavior_type, time_value)
            DO UPDATE SET count_value = count_value + 1
            """,
            rows,
        )

    def suspicious_summary(self, threshold: int) -> dict[str, Any]:
        row = self.connection.execute(
            """
            SELECT
                COUNT(*),
                COALESCE(SUM(count_value), 0),
                COALESCE(MAX(count_value), 0)
            FROM repeat_counts
            WHERE count_value >= ?
            """,
            (threshold,),
        ).fetchone()
        groups = int(row[0])
        rows = int(row[1])
        max_group_size = int(row[2])

        distribution: dict[str, dict[str, int]] = {}
        for behavior_type, group_count, row_count in self.connection.execute(
            """
            SELECT behavior_type, COUNT(*), SUM(count_value)
            FROM repeat_counts
            WHERE count_value >= ?
            GROUP BY behavior_type
            ORDER BY behavior_type
            """,
            (threshold,),
        ):
            distribution[str(int(behavior_type))] = {
                "behavior_name": BEHAVIOR_MAPPING[int(behavior_type)],
                "groups": int(group_count),
                "rows": int(row_count),
            }

        return {
            "threshold": threshold,
            "groups": groups,
            "rows": rows,
            "rows_removed_if_collapsed_to_one": rows - groups,
            "max_group_size": max_group_size,
            "behavior_distribution": distribution,
        }

    def suspicious_keys(self, threshold: int) -> set[tuple[int, int, int, str]]:
        return {
            (int(user_id), int(item_id), int(behavior_type), str(time_value))
            for user_id, item_id, behavior_type, time_value in self.connection.execute(
                """
                SELECT user_id, item_id, behavior_type, time_value
                FROM repeat_counts
                WHERE count_value >= ?
                """,
                (threshold,),
            )
        }

    def commit(self) -> None:
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()


def _validate_paths(
    input_csv: Path,
    output_csv: Path,
    output_parquet: Path | None,
    report_path: Path | None,
) -> None:
    if not input_csv.is_file():
        raise FileNotFoundError(f"Input CSV not found: {input_csv}")

    resolved_input = input_csv.resolve()
    targets = [output_csv]
    if output_parquet is not None:
        targets.append(output_parquet)
    if report_path is not None:
        targets.append(report_path)
    resolved_targets = [target.resolve() for target in targets]
    if resolved_input in resolved_targets:
        raise ValueError("The raw input path cannot be used as an output path")
    if len(resolved_targets) != len(set(resolved_targets)):
        raise ValueError("Output paths must be distinct")


def _validate_columns(input_csv: Path, encoding: str) -> None:
    columns = pd.read_csv(input_csv, encoding=encoding, nrows=0).columns.tolist()
    if columns != EXPECTED_COLUMNS:
        raise ValueError(
            "CSV columns do not match the project schema. "
            f"Expected {EXPECTED_COLUMNS}, got {columns}"
        )


def _validate_clean_chunk(chunk: pd.DataFrame) -> None:
    if chunk.columns.tolist() != OUTPUT_COLUMNS:
        raise RuntimeError("Internal error: clean output columns are incorrect")
    if chunk[OUTPUT_COLUMNS].isna().any().any():
        raise RuntimeError("Internal error: clean output contains missing values")
    if not chunk["behavior_type"].isin(BEHAVIOR_MAPPING).all():
        raise RuntimeError("Internal error: clean output has invalid behavior_type")
    expected_names = chunk["behavior_type"].map(BEHAVIOR_MAPPING)
    if not expected_names.eq(chunk["behavior_name"]).all():
        raise RuntimeError("Internal error: behavior_name mapping is incorrect")
    if not chunk["behavior_hour"].between(0, 23).all():
        raise RuntimeError("Internal error: behavior_hour is outside 0..23")
    if not chunk["weekday"].between(0, 6).all():
        raise RuntimeError("Internal error: weekday is outside 0..6")


def validate_clean_output(
    csv_path: Path | str,
    *,
    expected_rows: int | None = None,
    parquet_path: Path | str | None = None,
    chunksize: int = 100_000,
    allowed_start: str | pd.Timestamp | None = None,
    allowed_end: str | pd.Timestamp | None = None,
    suspicious_repeat_threshold: int = DEFAULT_SUSPICIOUS_REPEAT_THRESHOLD,
) -> dict[str, Any]:
    """Independently validate a clean CSV under the current repeat policy.

    Repeated four-field keys are allowed when their global count is below the
    suspicious threshold. A clean output is invalid if any such group still has
    ``threshold`` or more rows.
    """

    csv_path = Path(csv_path)
    parquet_path = Path(parquet_path) if parquet_path is not None else None
    if chunksize <= 0:
        raise ValueError("chunksize must be a positive integer")
    if suspicious_repeat_threshold < 2:
        raise ValueError("suspicious_repeat_threshold must be at least 2")

    allowed_start_ts = _parse_time_boundary(allowed_start, name="allowed_start")
    allowed_end_ts = _parse_time_boundary(allowed_end, name="allowed_end")
    if (
        allowed_start_ts is not None
        and allowed_end_ts is not None
        and allowed_start_ts > allowed_end_ts
    ):
        raise ValueError("allowed_start must be <= allowed_end")

    if not csv_path.is_file():
        raise FileNotFoundError(f"Clean CSV not found: {csv_path}")
    columns = pd.read_csv(csv_path, nrows=0).columns.tolist()
    if columns != OUTPUT_COLUMNS:
        raise ValueError(
            f"Clean CSV columns are incorrect: expected {OUTPUT_COLUMNS}, got {columns}"
        )

    validation_database = _temporary_path(csv_path, ".validation.sqlite.tmp")
    connection: sqlite3.Connection | None = None
    total_rows = 0
    try:
        connection = sqlite3.connect(validation_database)
        connection.execute("PRAGMA journal_mode = OFF")
        connection.execute("PRAGMA synchronous = OFF")
        connection.execute(
            """
            CREATE TABLE clean_key_counts (
                user_id INTEGER NOT NULL,
                item_id INTEGER NOT NULL,
                behavior_type INTEGER NOT NULL,
                time_value TEXT NOT NULL,
                count_value INTEGER NOT NULL,
                PRIMARY KEY (user_id, item_id, behavior_type, time_value)
            ) WITHOUT ROWID
            """
        )

        reader = pd.read_csv(
            csv_path,
            dtype={column: "string" for column in OUTPUT_COLUMNS},
            keep_default_na=False,
            na_filter=False,
            chunksize=chunksize,
        )
        for chunk_number, chunk in enumerate(reader, start=1):
            if chunk.eq("").any().any():
                raise ValueError(
                    f"Clean CSV has missing values in chunk {chunk_number}"
                )

            for column in ("user_id", "item_id", "category_id"):
                parsed_id, valid_id = _parse_identifier(chunk[column])
                if not valid_id.all() or parsed_id.isna().any():
                    raise ValueError(
                        f"Clean CSV has an invalid {column} in chunk {chunk_number}"
                    )

            valid_behavior = chunk["behavior_type"].isin(
                {str(value) for value in BEHAVIOR_MAPPING}
            )
            if not valid_behavior.all():
                raise ValueError(
                    f"Clean CSV has invalid behavior_type in chunk {chunk_number}"
                )
            expected_names = chunk["behavior_type"].map(
                {str(key): value for key, value in BEHAVIOR_MAPPING.items()}
            )
            if not expected_names.eq(chunk["behavior_name"]).all():
                raise ValueError(
                    f"Clean CSV has an invalid behavior_name in chunk {chunk_number}"
                )

            time_format_ok = chunk["time"].str.fullmatch(
                r"[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}",
                na=False,
            )
            parsed_time = pd.to_datetime(
                chunk["time"].where(time_format_ok),
                format=TIME_OUTPUT_FORMAT,
                errors="coerce",
                exact=True,
            )
            if parsed_time.isna().any():
                raise ValueError(
                    f"Clean CSV has unparseable time in chunk {chunk_number}"
                )
            if allowed_start_ts is not None and parsed_time.lt(allowed_start_ts).any():
                raise ValueError(
                    f"Clean CSV has time earlier than allowed_start in chunk {chunk_number}"
                )
            if allowed_end_ts is not None and parsed_time.gt(allowed_end_ts).any():
                raise ValueError(
                    f"Clean CSV has time later than allowed_end in chunk {chunk_number}"
                )

            if not chunk["behavior_date"].eq(
                parsed_time.dt.strftime("%Y-%m-%d")
            ).all():
                raise ValueError(
                    f"Clean CSV has an invalid behavior_date in chunk {chunk_number}"
                )
            if not pd.to_numeric(chunk["behavior_hour"], errors="coerce").eq(
                parsed_time.dt.hour
            ).all():
                raise ValueError(
                    f"Clean CSV has an invalid behavior_hour in chunk {chunk_number}"
                )
            if not pd.to_numeric(chunk["weekday"], errors="coerce").eq(
                parsed_time.dt.weekday
            ).all():
                raise ValueError(
                    f"Clean CSV has an invalid weekday in chunk {chunk_number}"
                )

            rows = [
                (int(user_id), int(item_id), int(behavior_type), str(time_value))
                for user_id, item_id, behavior_type, time_value in chunk[
                    ["user_id", "item_id", "behavior_type", "time"]
                ].itertuples(index=False, name=None)
            ]
            connection.executemany(
                """
                INSERT INTO clean_key_counts
                (user_id, item_id, behavior_type, time_value, count_value)
                VALUES (?, ?, ?, ?, 1)
                ON CONFLICT(user_id, item_id, behavior_type, time_value)
                DO UPDATE SET count_value = count_value + 1
                """,
                rows,
            )
            total_rows += len(chunk)
            connection.commit()

        if expected_rows is not None and total_rows != expected_rows:
            raise ValueError(
                f"Clean CSV row count mismatch: {total_rows:,} != {expected_rows:,}"
            )

        unique_key_rows = int(
            connection.execute("SELECT COUNT(*) FROM clean_key_counts").fetchone()[0]
        )
        max_repeat_group_size = int(
            connection.execute(
                "SELECT COALESCE(MAX(count_value), 0) FROM clean_key_counts"
            ).fetchone()[0]
        )
        suspicious_groups_remaining = int(
            connection.execute(
                "SELECT COUNT(*) FROM clean_key_counts WHERE count_value >= ?",
                (suspicious_repeat_threshold,),
            ).fetchone()[0]
        )
        if suspicious_groups_remaining:
            raise ValueError(
                "Clean CSV still contains "
                f"{suspicious_groups_remaining:,} repeat groups with at least "
                f"{suspicious_repeat_threshold} rows"
            )

        parquet_rows = None
        if parquet_path is not None:
            if not parquet_path.is_file():
                raise FileNotFoundError(f"Clean Parquet not found: {parquet_path}")
            parquet_file = pq.ParquetFile(parquet_path)
            try:
                parquet_rows = parquet_file.metadata.num_rows
                parquet_columns = parquet_file.schema_arrow.names
            finally:
                parquet_file.close()
            if parquet_columns != OUTPUT_COLUMNS:
                raise ValueError(
                    "Clean Parquet columns do not match the clean CSV schema"
                )
            if parquet_rows != total_rows:
                raise ValueError(
                    f"Parquet row count mismatch: {parquet_rows:,} != {total_rows:,}"
                )

        return {
            "valid": True,
            "csv_rows": total_rows,
            "parquet_rows": parquet_rows,
            "unique_clean_key_rows": unique_key_rows,
            "repeated_clean_key_rows_preserved": total_rows - unique_key_rows,
            "max_repeat_group_size": max_repeat_group_size,
            "suspicious_repeat_threshold": suspicious_repeat_threshold,
            "suspicious_groups_remaining": suspicious_groups_remaining,
            "columns": OUTPUT_COLUMNS,
        }
    finally:
        if connection is not None:
            connection.close()
        validation_database.unlink(missing_ok=True)


def _format_time(value: pd.Timestamp | None) -> str | None:
    return None if value is None else value.strftime(TIME_OUTPUT_FORMAT)


def _display_path(path: Path | None) -> str | None:
    """Return a repository-relative path when possible for portable reports."""

    if path is None:
        return None
    try:
        return path.resolve().relative_to(PROJECT_ROOT.resolve()).as_posix()
    except ValueError:
        return str(path)


def _make_report(
    *,
    input_csv: Path,
    output_csv: Path,
    output_parquet: Path | None,
    total_rows: int,
    clean_rows: int,
    unique_values: dict[str, set[str]],
    behavior_distribution: Counter[str],
    time_min: pd.Timestamp | None,
    time_max: pd.Timestamp | None,
    missing_by_field: Counter[str],
    missing_records: int,
    invalid_behavior_rows: int,
    invalid_id_rows: int,
    invalid_id_by_field: Counter[str],
    unparseable_time_rows: int,
    out_of_range_time_rows: int,
    allowed_start: pd.Timestamp | None,
    allowed_end: pd.Timestamp | None,
    fully_duplicate_rows: int,
    repeated_quad_rows: int,
    suspicious_summary: dict[str, Any],
    removal_by_reason: Counter[str],
    validation: dict[str, Any],
    elapsed_seconds: float,
) -> dict[str, Any]:
    removed_rows = total_rows - clean_rows
    removal_sum = sum(removal_by_reason.values())
    if removed_rows != removal_sum:
        raise RuntimeError(
            "Cleaning reconciliation failed: "
            f"removed={removed_rows}, reasons={removal_sum}"
        )

    range_configured = allowed_start is not None or allowed_end is not None
    return {
        "schema_version": 2,
        "input": _display_path(input_csv),
        "outputs": {
            "csv": _display_path(output_csv),
            "parquet": _display_path(output_parquet),
        },
        "rules": {
            "behavior_mapping": {
                str(key): value for key, value in BEHAVIOR_MAPPING.items()
            },
            "id_validation": (
                "Non-empty positive integer in the existing Int64/SQLite INTEGER "
                "representation; no project-specific business range is imposed."
            ),
            "time_validation": {
                "format": TIME_INPUT_FORMAT,
                "allowed_start": _format_time(allowed_start),
                "allowed_end": _format_time(allowed_end),
                "range_check_configured": range_configured,
            },
            "repeat_policy": {
                "key": ["user_id", "item_id", "behavior_type", "time"],
                "source_time_granularity": "hour",
                "preserve_normal_repeats": True,
                "suspicious_repeat_threshold": suspicious_summary["threshold"],
                "threshold_inclusive": True,
                "action": (
                    "For a valid key repeated at least the threshold within the same "
                    "source hour, keep the first row and remove the remaining rows."
                ),
                "limitation": (
                    "Minute-level bursts cannot be identified because the source time "
                    "field is only precise to the hour. The same-hour threshold is the "
                    "operational proxy used by this pipeline."
                ),
            },
            "weekday": "Monday=0 through Sunday=6",
        },
        "quality": {
            "total_rows": total_rows,
            "unique_user_id": len(unique_values["user_id"]),
            "unique_item_id": len(unique_values["item_id"]),
            "unique_item_category": len(unique_values["item_category"]),
            "behavior_type_distribution": dict(sorted(behavior_distribution.items())),
            "time_min": _format_time(time_min),
            "time_max": _format_time(time_max),
            "missing_by_field": {
                column: int(missing_by_field[column]) for column in EXPECTED_COLUMNS
            },
            "records_with_missing_critical_field": missing_records,
            "invalid_behavior_type_rows": invalid_behavior_rows,
            "invalid_id_rows": invalid_id_rows,
            "invalid_id_by_field": {
                column: int(invalid_id_by_field[column]) for column in ID_COLUMNS
            },
            "unparseable_time_rows": unparseable_time_rows,
            "time_range_check": {
                "configured": range_configured,
                "allowed_start": _format_time(allowed_start),
                "allowed_end": _format_time(allowed_end),
                "out_of_range_time_rows": (
                    out_of_range_time_rows if range_configured else None
                ),
            },
            "fully_duplicate_rows_diagnostic_only": fully_duplicate_rows,
            "repeated_user_item_behavior_time_rows_diagnostic_only": repeated_quad_rows,
            "suspicious_repeat_bursts": suspicious_summary,
        },
        "cleaning": {
            "original_rows": total_rows,
            "clean_rows": clean_rows,
            "removed_rows": removed_rows,
            "removal_ratio": (removed_rows / total_rows) if total_rows else 0.0,
            "removal_ratio_percent": (
                round(removed_rows * 100 / total_rows, 6) if total_rows else 0.0
            ),
            "issue_counts_may_overlap": {
                "records_with_missing_critical_field": missing_records,
                "invalid_behavior_type_rows": invalid_behavior_rows,
                "invalid_id_rows": invalid_id_rows,
                "unparseable_time_rows": unparseable_time_rows,
                "out_of_range_time_rows": (
                    out_of_range_time_rows if range_configured else None
                ),
                "fully_duplicate_rows_diagnostic_only": fully_duplicate_rows,
                "repeated_user_item_behavior_time_rows_diagnostic_only": repeated_quad_rows,
                "suspicious_repeat_rows": suspicious_summary["rows"],
            },
            "removed_by_mutually_exclusive_reason": {
                "missing_critical_field": int(
                    removal_by_reason["missing_critical_field"]
                ),
                "invalid_behavior_type": int(
                    removal_by_reason["invalid_behavior_type"]
                ),
                "invalid_id": int(removal_by_reason["invalid_id"]),
                "unparseable_time": int(removal_by_reason["unparseable_time"]),
                "out_of_range_time": int(removal_by_reason["out_of_range_time"]),
                "suspicious_repeat_burst": int(
                    removal_by_reason["suspicious_repeat_burst"]
                ),
            },
            "normal_repeated_events_preserved": True,
            "reconciled": True,
        },
        "output_validation": validation,
        "elapsed_seconds": round(elapsed_seconds, 3),
    }


def render_markdown_report(report: dict[str, Any]) -> str:
    """Render the machine-internal report dictionary as the formal Markdown report."""

    quality = report["quality"]
    cleaning = report["cleaning"]
    rules = report["rules"]
    validation = report["output_validation"]
    burst = quality["suspicious_repeat_bursts"]
    time_range = quality["time_range_check"]

    def number(value: Any) -> str:
        return "未配置/不适用" if value is None else f"{int(value):,}"

    def behavior_sort_key(value: str) -> tuple[int, int | str]:
        try:
            return (0, int(value))
        except (TypeError, ValueError):
            return (1, str(value))

    def behavior_name_for_report(value: str) -> str:
        try:
            return BEHAVIOR_MAPPING.get(int(value), "非法/未定义")
        except (TypeError, ValueError):
            return "缺失/非法"

    behavior_rows = []
    for behavior_type in sorted(
        quality["behavior_type_distribution"], key=behavior_sort_key
    ):
        behavior_rows.append(
            f"| {behavior_type} | {behavior_name_for_report(behavior_type)} | "
            f"{int(quality['behavior_type_distribution'][behavior_type]):,} |"
        )

    burst_behavior_rows = []
    for behavior_type, values in burst["behavior_distribution"].items():
        burst_behavior_rows.append(
            f"| {behavior_type} | {values['behavior_name']} | "
            f"{values['groups']:,} | {values['rows']:,} |"
        )
    if not burst_behavior_rows:
        burst_behavior_rows.append("| - | - | 0 | 0 |")

    removed = cleaning["removed_by_mutually_exclusive_reason"]
    missing = quality["missing_by_field"]
    invalid_ids = quality["invalid_id_by_field"]

    lines = [
        "# Member 2 数据质量与清洗处理报告",
        "",
        "> 本报告由 `scripts/run_user_behavior_cleaning.py` 在全量清洗完成后自动生成。",
        "",
        "## 1. 数据与输出说明",
        "",
        f"- 输入：`{report['input']}`",
        f"- clean CSV：`{report['outputs']['csv']}`",
        f"- clean Parquet：`{report['outputs']['parquet'] or '未生成'}`",
        f"- 原始记录数：**{cleaning['original_rows']:,}**",
        f"- 清洗后记录数：**{cleaning['clean_rows']:,}**",
        f"- 实际删除记录数：**{cleaning['removed_rows']:,}**",
        f"- 删除比例：**{cleaning['removal_ratio_percent']:.6f}%**",
        f"- 原始可解析时间范围：`{quality['time_min']}` ～ `{quality['time_max']}`",
        "",
        "## 2. 重复行为与异常高频规则",
        "",
        "本项目输入字段 `time` 只精确到小时，因此同一用户在同一小时内可能真实发生多次浏览、收藏、加购或购买。",
        "所以，**相同 `user_id + item_id + behavior_type + time` 不再被一律视为应删除重复数据**。",
        "",
        f"当前异常高频阈值为 **{burst['threshold']} 次及以上**。由于没有分钟级时间戳，程序只能在同一小时粒度下执行该规则：",
        "",
        f"- 同一四元组出现 **2～{burst['threshold'] - 1} 次**：全部保留；",
        f"- 同一四元组出现 **{burst['threshold']} 次及以上**：标记为异常高频/疑似恶意重复组，只保留首次记录，其余删除；",
        "- 此规则是小时粒度代理规则，**不能声称识别了‘一分钟内 60 次’**。若后续获得分钟/秒级时间戳，应改用真实短时间窗口检测。",
        "",
        "### 2.1 重复统计（诊断项，不等于删除量）",
        "",
        "| 检查项 | 记录数 | 处理方式 |",
        "| --- | ---: | --- |",
        f"| 完全重复记录（首条之后的重复行） | {quality['fully_duplicate_rows_diagnostic_only']:,} | 仅诊断，不因重复本身删除 |",
        f"| 四元组重复记录（首条之后） | {quality['repeated_user_item_behavior_time_rows_diagnostic_only']:,} | 阈值以下全部保留 |",
        "",
        "### 2.2 异常高频组",
        "",
        "| 指标 | 数值 |",
        "| --- | ---: |",
        f"| 阈值 | {burst['threshold']} |",
        f"| 异常高频组数 | {burst['groups']:,} |",
        f"| 异常高频组涉及记录数 | {burst['rows']:,} |",
        f"| 因异常高频实际删除记录数 | {removed['suspicious_repeat_burst']:,} |",
        f"| 异常高频组最大出现次数 | {burst['max_group_size']:,} |",
        "",
        "按行为类型分布：",
        "",
        "| behavior_type | behavior_name | 异常组数 | 涉及记录数 |",
        "| --- | --- | ---: | ---: |",
        *burst_behavior_rows,
        "",
        "## 3. 数据质量检查",
        "",
        "### 3.1 数据规模",
        "",
        "| 指标 | 数值 |",
        "| --- | ---: |",
        f"| 总行数 | {quality['total_rows']:,} |",
        f"| 用户数 | {quality['unique_user_id']:,} |",
        f"| 商品数 | {quality['unique_item_id']:,} |",
        f"| 类目数 | {quality['unique_item_category']:,} |",
        "",
        "### 3.2 行为类型分布（原始输入）",
        "",
        "| behavior_type | behavior_name | 行数 |",
        "| --- | --- | ---: |",
        *behavior_rows,
        "",
        "### 3.3 缺失、非法 ID 与时间检查",
        "",
        "| 检查项 | 数量 |",
        "| --- | ---: |",
        f"| 缺失 time | {missing['time']:,} |",
        f"| 缺失 user_id | {missing['user_id']:,} |",
        f"| 缺失 item_id | {missing['item_id']:,} |",
        f"| 缺失 item_category | {missing['item_category']:,} |",
        f"| 缺失 behavior_type | {missing['behavior_type']:,} |",
        f"| 至少一个关键字段缺失 | {quality['records_with_missing_critical_field']:,} |",
        f"| 非法 behavior_type | {quality['invalid_behavior_type_rows']:,} |",
        f"| 非法 user_id | {invalid_ids['user_id']:,} |",
        f"| 非法 item_id | {invalid_ids['item_id']:,} |",
        f"| 非法 item_category | {invalid_ids['item_category']:,} |",
        f"| 任一非法 ID | {quality['invalid_id_rows']:,} |",
        f"| 无法解析时间 | {quality['unparseable_time_rows']:,} |",
        f"| 超出配置合法时间范围 | {number(time_range['out_of_range_time_rows'])} |",
        "",
        f"合法时间范围检查是否配置：**{'是' if time_range['configured'] else '否'}**。",
        f"配置起点：`{time_range['allowed_start'] or '未配置'}`；配置终点：`{time_range['allowed_end'] or '未配置'}`。",
        "",
        "## 4. 清洗规则",
        "",
        "1. 关键字段缺失记录剔除。",
        "2. `behavior_type` 仅允许 1/2/3/4，并映射为 pv/fav/cart/buy。",
        "3. ID 要求为非空正整数且可安全表示为 Int64/SQLite INTEGER；不对 ID 使用 IQR/3σ。",
        f"4. `time` 按 `{TIME_INPUT_FORMAT}` 严格解析；配置业务合法时间范围时同时剔除越界记录。",
        "5. `item_category` 标准化为 `category_id`。",
        "6. 生成 `behavior_name`、`behavior_date`、`behavior_hour`、`weekday`。",
        f"7. 普通四元组重复不删除；只有同一小时内相同四元组达到 {burst['threshold']} 次及以上时才视为异常高频并折叠为一条。",
        "8. 使用分块读取和磁盘 SQLite 统计，保证跨 chunk 的全局规则一致。",
        "",
        "## 5. 清洗前后对比",
        "",
        "| 指标 | 数值 |",
        "| --- | ---: |",
        f"| 原始记录数 | {cleaning['original_rows']:,} |",
        f"| 清洗后记录数 | {cleaning['clean_rows']:,} |",
        f"| 删除记录数 | {cleaning['removed_rows']:,} |",
        f"| 删除比例 | {cleaning['removal_ratio_percent']:.6f}% |",
        "",
        "互斥删除原因：",
        "",
        "| 删除原因 | 删除行数 |",
        "| --- | ---: |",
        f"| 缺失关键字段 | {removed['missing_critical_field']:,} |",
        f"| 非法 behavior_type | {removed['invalid_behavior_type']:,} |",
        f"| 非法 ID | {removed['invalid_id']:,} |",
        f"| 无法解析时间 | {removed['unparseable_time']:,} |",
        f"| 超出合法时间范围 | {number(removed['out_of_range_time'] if time_range['configured'] else None)} |",
        f"| 异常高频重复 | {removed['suspicious_repeat_burst']:,} |",
        "",
        f"删除原因合计与总删除数对账：**{'通过' if cleaning['reconciled'] else '失败'}**。",
        "",
        "## 6. 实际输出回读验证",
        "",
        f"- 验证状态：**{'通过' if validation['valid'] else '失败'}**",
        f"- CSV 实际行数：{validation['csv_rows']:,}",
        f"- Parquet 实际行数：{number(validation['parquet_rows'])}",
        f"- clean 中保留的正常重复行（首条之外）：{validation['repeated_clean_key_rows_preserved']:,}",
        f"- clean 中最大四元组重复次数：{validation['max_repeat_group_size']:,}",
        f"- clean 中仍达到异常阈值的组数：{validation['suspicious_groups_remaining']:,}",
        "",
        "验证会实际重新读取 clean CSV（以及可选 Parquet），而不是仅通过删除数量推导结果。",
        "",
        "## 7. 性能信息",
        "",
        f"- 全量流程耗时：{report['elapsed_seconds']:.3f} 秒。",
        "",
        "## 8. 后续使用说明",
        "",
        "Member 3 与后续 EDA 应基于 `data/processed/user_behavior_clean.parquet`（或 clean CSV）重新计算正式统计指标。",
        "旧版报告中把所有四元组重复都删除的口径已废弃，不能继续使用旧版 clean 行数或旧版删除比例作为最终结论。",
        "",
    ]
    return "\n".join(lines)


def clean_user_behavior(
    input_csv: Path | str,
    output_csv: Path | str,
    *,
    output_parquet: Path | str | None = None,
    report_path: Path | str | None = None,
    allowed_start: str | pd.Timestamp | None = None,
    allowed_end: str | pd.Timestamp | None = None,
    suspicious_repeat_threshold: int = DEFAULT_SUSPICIOUS_REPEAT_THRESHOLD,
    chunksize: int = 100_000,
    encoding: str = "utf-8-sig",
    progress: bool = True,
) -> CleaningResult:
    """Quality-check and clean the input CSV using two streaming passes.

    Pass 1 calculates global quality statistics and exact same-hour repeat
    counts. Pass 2 writes the clean outputs while preserving normal repeats and
    collapsing only suspicious repeat bursts.
    """

    input_csv = Path(input_csv)
    output_csv = Path(output_csv)
    output_parquet = Path(output_parquet) if output_parquet is not None else None
    report_path = Path(report_path) if report_path is not None else None

    if chunksize <= 0:
        raise ValueError("chunksize must be a positive integer")
    if suspicious_repeat_threshold < 2:
        raise ValueError("suspicious_repeat_threshold must be at least 2")

    allowed_start_ts = _parse_time_boundary(allowed_start, name="allowed_start")
    allowed_end_ts = _parse_time_boundary(allowed_end, name="allowed_end")
    if (
        allowed_start_ts is not None
        and allowed_end_ts is not None
        and allowed_start_ts > allowed_end_ts
    ):
        raise ValueError("allowed_start must be <= allowed_end")

    _validate_paths(input_csv, output_csv, output_parquet, report_path)
    _validate_columns(input_csv, encoding)

    output_csv.parent.mkdir(parents=True, exist_ok=True)
    if output_parquet is not None:
        output_parquet.parent.mkdir(parents=True, exist_ok=True)
    if report_path is not None:
        report_path.parent.mkdir(parents=True, exist_ok=True)

    temp_csv = _temporary_path(output_csv, ".csv.tmp")
    temp_parquet = (
        _temporary_path(output_parquet, ".parquet.tmp")
        if output_parquet is not None
        else None
    )
    temp_report = (
        _temporary_path(report_path, ".md.tmp") if report_path is not None else None
    )
    temp_database = _temporary_path(output_csv, ".quality.sqlite.tmp")

    tracker: _DiskQualityTracker | None = None
    parquet_writer: pq.ParquetWriter | None = None
    started_at = time.perf_counter()

    total_rows = 0
    clean_rows = 0
    unique_values = {column: set() for column in ID_COLUMNS}
    behavior_distribution: Counter[str] = Counter()
    missing_by_field: Counter[str] = Counter()
    invalid_id_by_field: Counter[str] = Counter()
    removal_by_reason: Counter[str] = Counter()
    missing_records = 0
    invalid_behavior_rows = 0
    invalid_id_rows = 0
    unparseable_time_rows = 0
    out_of_range_time_rows = 0
    fully_duplicate_rows = 0
    repeated_quad_rows = 0
    time_min: pd.Timestamp | None = None
    time_max: pd.Timestamp | None = None

    try:
        tracker = _DiskQualityTracker(temp_database)

        # Pass 1: quality statistics and exact global repeat counts.
        reader = pd.read_csv(
            input_csv,
            encoding=encoding,
            dtype={column: "string" for column in EXPECTED_COLUMNS},
            keep_default_na=False,
            na_filter=False,
            chunksize=chunksize,
        )
        for chunk_number, raw_chunk in enumerate(reader, start=1):
            total_rows += len(raw_chunk)
            full_duplicates, quad_duplicates = tracker.raw_duplicate_counts(raw_chunk)
            fully_duplicate_rows += full_duplicates
            repeated_quad_rows += quad_duplicates

            analysis = _analyze_chunk(
                raw_chunk,
                allowed_start=allowed_start_ts,
                allowed_end=allowed_end_ts,
            )
            for column in EXPECTED_COLUMNS:
                missing_by_field[column] += int(
                    analysis.missing_masks[column].sum()
                )
            missing_records += int(analysis.missing_any.sum())

            for column in ID_COLUMNS:
                unique_values[column].update(
                    analysis.stripped.loc[
                        ~analysis.missing_masks[column], column
                    ].tolist()
                )
                invalid_for_column = (
                    ~analysis.missing_masks[column]
                    & ~analysis.valid_id_masks[column]
                )
                invalid_id_by_field[column] += int(invalid_for_column.sum())

            invalid_id_rows += int(analysis.invalid_id_mask.sum())
            invalid_behavior_rows += int(analysis.invalid_behavior_mask.sum())
            unparseable_time_rows += int(analysis.invalid_time_mask.sum())
            out_of_range_time_rows += int(analysis.out_of_range_time_mask.sum())

            behavior_values = analysis.stripped["behavior_type"].mask(
                analysis.missing_masks["behavior_type"], "<missing>"
            )
            behavior_distribution.update(behavior_values.tolist())

            parseable_times = analysis.parsed_time.dropna()
            if not parseable_times.empty:
                chunk_min = parseable_times.min()
                chunk_max = parseable_times.max()
                time_min = chunk_min if time_min is None else min(time_min, chunk_min)
                time_max = chunk_max if time_max is None else max(time_max, chunk_max)

            candidates = _clean_frame_from_analysis(
                analysis, analysis.base_valid_mask
            )
            tracker.add_repeat_counts(candidates)
            tracker.commit()
            if progress:
                print(
                    f"Pass 1 chunk {chunk_number}: raw_total={total_rows:,}, "
                    "quality/repeat counts updated"
                )

        if total_rows == 0:
            raise ValueError("CSV contains a header but no data rows")

        suspicious_summary = tracker.suspicious_summary(
            suspicious_repeat_threshold
        )
        suspicious_keys = tracker.suspicious_keys(suspicious_repeat_threshold)

        # Pass 2: perform cleaning and apply the threshold-based repeat policy.
        csv_header_written = False
        seen_suspicious_keys: set[tuple[int, int, int, str]] = set()
        reader = pd.read_csv(
            input_csv,
            encoding=encoding,
            dtype={column: "string" for column in EXPECTED_COLUMNS},
            keep_default_na=False,
            na_filter=False,
            chunksize=chunksize,
        )
        for chunk_number, raw_chunk in enumerate(reader, start=1):
            analysis = _analyze_chunk(
                raw_chunk,
                allowed_start=allowed_start_ts,
                allowed_end=allowed_end_ts,
            )

            remaining = ~analysis.missing_any
            removal_by_reason["missing_critical_field"] += int(
                analysis.missing_any.sum()
            )

            remove_mask = remaining & analysis.invalid_behavior_mask
            removal_by_reason["invalid_behavior_type"] += int(remove_mask.sum())
            remaining &= ~analysis.invalid_behavior_mask

            remove_mask = remaining & analysis.invalid_id_mask
            removal_by_reason["invalid_id"] += int(remove_mask.sum())
            remaining &= ~analysis.invalid_id_mask

            remove_mask = remaining & analysis.invalid_time_mask
            removal_by_reason["unparseable_time"] += int(remove_mask.sum())
            remaining &= ~analysis.invalid_time_mask

            remove_mask = remaining & analysis.out_of_range_time_mask
            removal_by_reason["out_of_range_time"] += int(remove_mask.sum())
            remaining &= ~analysis.out_of_range_time_mask

            clean_chunk = _clean_frame_from_analysis(analysis, remaining)
            keys = _repeat_keys_from_clean_chunk(clean_chunk)
            keep = []
            removed_suspicious = 0
            for key in keys:
                if key not in suspicious_keys:
                    keep.append(True)
                    continue
                if key in seen_suspicious_keys:
                    keep.append(False)
                    removed_suspicious += 1
                else:
                    seen_suspicious_keys.add(key)
                    keep.append(True)

            removal_by_reason["suspicious_repeat_burst"] += removed_suspicious
            if keep:
                clean_chunk = clean_chunk.loc[
                    pd.Series(keep, index=clean_chunk.index, dtype=bool)
                ].reset_index(drop=True)
            _validate_clean_chunk(clean_chunk)

            if not clean_chunk.empty:
                clean_chunk.to_csv(
                    temp_csv,
                    mode="a",
                    header=not csv_header_written,
                    index=False,
                    encoding="utf-8",
                    date_format=TIME_OUTPUT_FORMAT,
                )
                csv_header_written = True

                if temp_parquet is not None:
                    arrow_table = pa.Table.from_pandas(
                        clean_chunk,
                        preserve_index=False,
                    )
                    if parquet_writer is None:
                        parquet_writer = pq.ParquetWriter(
                            temp_parquet,
                            arrow_table.schema,
                            compression="snappy",
                        )
                    parquet_writer.write_table(arrow_table)

            clean_rows += len(clean_chunk)
            if progress:
                print(
                    f"Pass 2 chunk {chunk_number}: clean_total={clean_rows:,}, "
                    f"suspicious_removed_total="
                    f"{removal_by_reason['suspicious_repeat_burst']:,}"
                )

        empty_frame = _empty_clean_frame()
        if not csv_header_written:
            empty_frame.to_csv(temp_csv, index=False, encoding="utf-8")
        if temp_parquet is not None and parquet_writer is None:
            empty_table = pa.Table.from_pandas(empty_frame, preserve_index=False)
            parquet_writer = pq.ParquetWriter(
                temp_parquet,
                empty_table.schema,
                compression="snappy",
            )
            parquet_writer.write_table(empty_table)
        if parquet_writer is not None:
            parquet_writer.close()
            parquet_writer = None

        expected_suspicious_removed = suspicious_summary[
            "rows_removed_if_collapsed_to_one"
        ]
        actual_suspicious_removed = int(
            removal_by_reason["suspicious_repeat_burst"]
        )
        if actual_suspicious_removed != expected_suspicious_removed:
            raise RuntimeError(
                "Suspicious repeat reconciliation failed: "
                f"expected={expected_suspicious_removed:,}, "
                f"actual={actual_suspicious_removed:,}"
            )

        validation = validate_clean_output(
            temp_csv,
            expected_rows=clean_rows,
            parquet_path=temp_parquet,
            chunksize=chunksize,
            allowed_start=allowed_start_ts,
            allowed_end=allowed_end_ts,
            suspicious_repeat_threshold=suspicious_repeat_threshold,
        )

        report = _make_report(
            input_csv=input_csv,
            output_csv=output_csv,
            output_parquet=output_parquet,
            total_rows=total_rows,
            clean_rows=clean_rows,
            unique_values=unique_values,
            behavior_distribution=behavior_distribution,
            time_min=time_min,
            time_max=time_max,
            missing_by_field=missing_by_field,
            missing_records=missing_records,
            invalid_behavior_rows=invalid_behavior_rows,
            invalid_id_rows=invalid_id_rows,
            invalid_id_by_field=invalid_id_by_field,
            unparseable_time_rows=unparseable_time_rows,
            out_of_range_time_rows=out_of_range_time_rows,
            allowed_start=allowed_start_ts,
            allowed_end=allowed_end_ts,
            fully_duplicate_rows=fully_duplicate_rows,
            repeated_quad_rows=repeated_quad_rows,
            suspicious_summary=suspicious_summary,
            removal_by_reason=removal_by_reason,
            validation=validation,
            elapsed_seconds=time.perf_counter() - started_at,
        )

        if temp_report is not None:
            temp_report.write_text(
                render_markdown_report(report),
                encoding="utf-8",
            )

        tracker.close()
        tracker = None
        temp_database.unlink(missing_ok=True)

        temp_csv.replace(output_csv)
        if temp_parquet is not None and output_parquet is not None:
            temp_parquet.replace(output_parquet)
        if temp_report is not None and report_path is not None:
            temp_report.replace(report_path)

        return CleaningResult(
            csv_path=output_csv,
            parquet_path=output_parquet,
            report_path=report_path,
            report=report,
        )
    except Exception:
        if parquet_writer is not None:
            parquet_writer.close()
        if tracker is not None:
            tracker.close()
        for temporary in (temp_csv, temp_parquet, temp_report, temp_database):
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        raise
