"""Chunked quality checks and cleaning for the user-behavior CSV."""

from __future__ import annotations

import json
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


@dataclass(frozen=True)
class CleaningResult:
    """Paths and statistics returned by :func:`clean_user_behavior`."""

    csv_path: Path
    parquet_path: Path | None
    report_path: Path | None
    report: dict[str, Any]


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


class _DiskDeduplicator:
    """Exact, disk-backed duplicate tracking across every CSV chunk."""

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

            CREATE TABLE clean_seen (
                source_row INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL,
                item_id INTEGER NOT NULL,
                behavior_type INTEGER NOT NULL,
                time_value TEXT NOT NULL,
                UNIQUE (user_id, item_id, behavior_type, time_value)
            );
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

    def keep_first_clean_keys(
        self,
        clean_chunk: pd.DataFrame,
        source_rows: pd.Series,
    ) -> pd.Series:
        if clean_chunk.empty:
            return pd.Series(False, index=clean_chunk.index, dtype=bool)

        time_values = clean_chunk["time"].dt.strftime(TIME_OUTPUT_FORMAT)
        rows = (
            (
                int(source_row),
                int(user_id),
                int(item_id),
                int(behavior_type),
                time_value,
            )
            for source_row, user_id, item_id, behavior_type, time_value in zip(
                source_rows,
                clean_chunk["user_id"],
                clean_chunk["item_id"],
                clean_chunk["behavior_type"],
                time_values,
            )
        )
        self.connection.executemany(
            """
            INSERT OR IGNORE INTO clean_seen
            (source_row, user_id, item_id, behavior_type, time_value)
            VALUES (?, ?, ?, ?, ?)
            """,
            rows,
        )
        first_source_row = int(source_rows.min())
        last_source_row = int(source_rows.max())
        accepted = {
            row[0]
            for row in self.connection.execute(
                """
                SELECT source_row
                FROM clean_seen
                WHERE source_row BETWEEN ? AND ?
                """,
                (first_source_row, last_source_row),
            )
        }
        return source_rows.map(lambda value: int(value) in accepted)

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
) -> dict[str, Any]:
    """Independently validate a clean CSV, including exact global duplicates."""

    csv_path = Path(csv_path)
    parquet_path = Path(parquet_path) if parquet_path is not None else None
    if chunksize <= 0:
        raise ValueError("chunksize must be a positive integer")
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
    duplicate_rows = 0
    try:
        connection = sqlite3.connect(validation_database)
        connection.execute("PRAGMA journal_mode = OFF")
        connection.execute("PRAGMA synchronous = OFF")
        connection.execute(
            """
            CREATE TABLE clean_keys (
                user_id TEXT NOT NULL,
                item_id TEXT NOT NULL,
                behavior_type TEXT NOT NULL,
                time_value TEXT NOT NULL,
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
            if not chunk["behavior_date"].eq(
                parsed_time.dt.strftime("%Y-%m-%d")
            ).all():
                raise ValueError(
                    f"Clean CSV has an invalid behavior_date in chunk {chunk_number}"
                )
            if not pd.to_numeric(
                chunk["behavior_hour"], errors="coerce"
            ).eq(parsed_time.dt.hour).all():
                raise ValueError(
                    f"Clean CSV has an invalid behavior_hour in chunk {chunk_number}"
                )
            if not pd.to_numeric(chunk["weekday"], errors="coerce").eq(
                parsed_time.dt.weekday
            ).all():
                raise ValueError(
                    f"Clean CSV has an invalid weekday in chunk {chunk_number}"
                )

            before = connection.total_changes
            connection.executemany(
                """
                INSERT OR IGNORE INTO clean_keys
                (user_id, item_id, behavior_type, time_value)
                VALUES (?, ?, ?, ?)
                """,
                chunk[
                    ["user_id", "item_id", "behavior_type", "time"]
                ].itertuples(index=False, name=None),
            )
            inserted = connection.total_changes - before
            duplicate_rows += len(chunk) - inserted
            total_rows += len(chunk)
            connection.commit()

        if duplicate_rows:
            raise ValueError(
                f"Clean CSV has {duplicate_rows:,} duplicate clean-key rows"
            )
        if expected_rows is not None and total_rows != expected_rows:
            raise ValueError(
                f"Clean CSV row count mismatch: {total_rows:,} != {expected_rows:,}"
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
            "duplicate_clean_key_rows": duplicate_rows,
            "columns": OUTPUT_COLUMNS,
        }
    finally:
        if connection is not None:
            connection.close()
        validation_database.unlink(missing_ok=True)


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
    fully_duplicate_rows: int,
    duplicate_quad_rows: int,
    removal_by_reason: Counter[str],
    elapsed_seconds: float,
) -> dict[str, Any]:
    removed_rows = total_rows - clean_rows
    removal_sum = sum(removal_by_reason.values())
    if removed_rows != removal_sum:
        raise RuntimeError(
            "Cleaning reconciliation failed: "
            f"removed={removed_rows}, reasons={removal_sum}"
        )

    def format_time(value: pd.Timestamp | None) -> str | None:
        return None if value is None else value.strftime(TIME_OUTPUT_FORMAT)

    return {
        "schema_version": 1,
        "input": str(input_csv),
        "outputs": {
            "csv": str(output_csv),
            "parquet": str(output_parquet) if output_parquet else None,
        },
        "rules": {
            "behavior_mapping": {
                str(key): value for key, value in BEHAVIOR_MAPPING.items()
            },
            "id_validation": (
                "Non-empty positive integer in the existing Int64/SQLite INTEGER "
                "representation; no project-specific business range is imposed."
            ),
            "time_validation": (
                f"Strict {TIME_INPUT_FORMAT} parsing; no date-range filter is imposed."
            ),
            "clean_duplicate_key": [
                "user_id",
                "item_id",
                "behavior_type",
                "time",
            ],
            "weekday": "Monday=0 through Sunday=6",
        },
        "quality": {
            "total_rows": total_rows,
            "unique_user_id": len(unique_values["user_id"]),
            "unique_item_id": len(unique_values["item_id"]),
            "unique_item_category": len(unique_values["item_category"]),
            "behavior_type_distribution": dict(
                sorted(behavior_distribution.items())
            ),
            "time_min": format_time(time_min),
            "time_max": format_time(time_max),
            "missing_by_field": {
                column: int(missing_by_field[column])
                for column in EXPECTED_COLUMNS
            },
            "records_with_missing_critical_field": missing_records,
            "invalid_behavior_type_rows": invalid_behavior_rows,
            "invalid_id_rows": invalid_id_rows,
            "invalid_id_by_field": {
                column: int(invalid_id_by_field[column]) for column in ID_COLUMNS
            },
            "unparseable_time_rows": unparseable_time_rows,
            "fully_duplicate_rows": fully_duplicate_rows,
            "duplicate_user_item_behavior_time_rows": duplicate_quad_rows,
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
                "fully_duplicate_rows": fully_duplicate_rows,
                "duplicate_user_item_behavior_time_rows": duplicate_quad_rows,
            },
            "removed_by_mutually_exclusive_reason": {
                "missing_critical_field": int(
                    removal_by_reason["missing_critical_field"]
                ),
                "invalid_behavior_type": int(
                    removal_by_reason["invalid_behavior_type"]
                ),
                "invalid_id": int(removal_by_reason["invalid_id"]),
                "unparseable_time": int(
                    removal_by_reason["unparseable_time"]
                ),
                "duplicate_clean_key": int(
                    removal_by_reason["duplicate_clean_key"]
                ),
            },
            "reconciled": True,
        },
        "elapsed_seconds": round(elapsed_seconds, 3),
    }


def clean_user_behavior(
    input_csv: Path | str,
    output_csv: Path | str,
    *,
    output_parquet: Path | str | None = None,
    report_path: Path | str | None = None,
    chunksize: int = 100_000,
    encoding: str = "utf-8-sig",
    progress: bool = True,
) -> CleaningResult:
    """Check and clean the input CSV without loading the complete file in memory."""

    input_csv = Path(input_csv)
    output_csv = Path(output_csv)
    output_parquet = Path(output_parquet) if output_parquet is not None else None
    report_path = Path(report_path) if report_path is not None else None
    if chunksize <= 0:
        raise ValueError("chunksize must be a positive integer")
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
        _temporary_path(report_path, ".json.tmp")
        if report_path is not None
        else None
    )
    temp_database = _temporary_path(output_csv, ".dedupe.sqlite.tmp")

    deduplicator: _DiskDeduplicator | None = None
    parquet_writer: pq.ParquetWriter | None = None
    csv_header_written = False
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
    fully_duplicate_rows = 0
    duplicate_quad_rows = 0
    time_min: pd.Timestamp | None = None
    time_max: pd.Timestamp | None = None
    started_at = time.perf_counter()

    try:
        deduplicator = _DiskDeduplicator(temp_database)
        reader = pd.read_csv(
            input_csv,
            encoding=encoding,
            dtype={column: "string" for column in EXPECTED_COLUMNS},
            keep_default_na=False,
            na_filter=False,
            chunksize=chunksize,
        )
        for chunk_number, raw_chunk in enumerate(reader, start=1):
            chunk_size = len(raw_chunk)
            source_rows = pd.Series(
                range(total_rows + 1, total_rows + chunk_size + 1),
                index=raw_chunk.index,
                dtype="int64",
            )
            total_rows += chunk_size

            full_duplicates, quad_duplicates = (
                deduplicator.raw_duplicate_counts(raw_chunk)
            )
            fully_duplicate_rows += full_duplicates
            duplicate_quad_rows += quad_duplicates

            stripped = raw_chunk.apply(lambda column: column.str.strip())
            missing_masks = stripped.eq("")
            for column in EXPECTED_COLUMNS:
                missing_by_field[column] += int(missing_masks[column].sum())
            missing_any = missing_masks.any(axis=1)
            missing_records += int(missing_any.sum())

            for column in ID_COLUMNS:
                unique_values[column].update(
                    stripped.loc[~missing_masks[column], column].tolist()
                )
            behavior_values = stripped["behavior_type"].mask(
                missing_masks["behavior_type"],
                "<missing>",
            )
            behavior_distribution.update(behavior_values.tolist())

            parsed_ids: dict[str, pd.Series] = {}
            valid_id_masks: dict[str, pd.Series] = {}
            for column in ID_COLUMNS:
                parsed_ids[column], valid_id_masks[column] = _parse_identifier(
                    stripped[column]
                )
                invalid_for_column = (
                    ~missing_masks[column] & ~valid_id_masks[column]
                )
                invalid_id_by_field[column] += int(invalid_for_column.sum())
            invalid_id_mask = pd.concat(
                [
                    ~missing_masks[column] & ~valid_id_masks[column]
                    for column in ID_COLUMNS
                ],
                axis=1,
            ).any(axis=1)
            invalid_id_rows += int(invalid_id_mask.sum())

            valid_behavior_mask = stripped["behavior_type"].isin(
                {str(value) for value in BEHAVIOR_MAPPING}
            )
            invalid_behavior_mask = (
                ~missing_masks["behavior_type"] & ~valid_behavior_mask
            )
            invalid_behavior_rows += int(invalid_behavior_mask.sum())

            parsed_time = _parse_time(stripped["time"])
            invalid_time_mask = ~missing_masks["time"] & parsed_time.isna()
            unparseable_time_rows += int(invalid_time_mask.sum())
            parseable_times = parsed_time.dropna()
            if not parseable_times.empty:
                chunk_min = parseable_times.min()
                chunk_max = parseable_times.max()
                time_min = chunk_min if time_min is None else min(time_min, chunk_min)
                time_max = chunk_max if time_max is None else max(time_max, chunk_max)

            remaining = ~missing_any
            remove_mask = remaining & invalid_behavior_mask
            removal_by_reason["invalid_behavior_type"] += int(remove_mask.sum())
            remaining &= ~invalid_behavior_mask

            remove_mask = remaining & invalid_id_mask
            removal_by_reason["invalid_id"] += int(remove_mask.sum())
            remaining &= ~invalid_id_mask

            remove_mask = remaining & invalid_time_mask
            removal_by_reason["unparseable_time"] += int(remove_mask.sum())
            remaining &= ~invalid_time_mask
            removal_by_reason["missing_critical_field"] += int(missing_any.sum())

            clean_chunk = pd.DataFrame(
                {
                    "time": parsed_time.loc[remaining],
                    "user_id": parsed_ids["user_id"].loc[remaining].astype("int64"),
                    "item_id": parsed_ids["item_id"].loc[remaining].astype("int64"),
                    "category_id": parsed_ids["item_category"]
                    .loc[remaining]
                    .astype("int64"),
                    "behavior_type": stripped.loc[
                        remaining, "behavior_type"
                    ].astype("uint8"),
                }
            )
            clean_chunk["behavior_name"] = clean_chunk["behavior_type"].map(
                BEHAVIOR_MAPPING
            ).astype("string")
            clean_chunk["behavior_date"] = clean_chunk["time"].dt.strftime(
                "%Y-%m-%d"
            ).astype("string")
            clean_chunk["behavior_hour"] = clean_chunk["time"].dt.hour.astype(
                "uint8"
            )
            clean_chunk["weekday"] = clean_chunk["time"].dt.weekday.astype(
                "uint8"
            )
            clean_chunk = clean_chunk[OUTPUT_COLUMNS]

            accepted_mask = deduplicator.keep_first_clean_keys(
                clean_chunk,
                source_rows.loc[remaining],
            )
            duplicate_clean_rows = len(clean_chunk) - int(accepted_mask.sum())
            removal_by_reason["duplicate_clean_key"] += duplicate_clean_rows
            clean_chunk = clean_chunk.loc[accepted_mask].reset_index(drop=True)
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
            deduplicator.commit()
            if progress:
                print(
                    f"Processed chunk {chunk_number}: raw={chunk_size:,}, "
                    f"total={total_rows:,}, clean={clean_rows:,}"
                )

        if total_rows == 0:
            raise ValueError("CSV contains a header but no data rows")

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
            fully_duplicate_rows=fully_duplicate_rows,
            duplicate_quad_rows=duplicate_quad_rows,
            removal_by_reason=removal_by_reason,
            elapsed_seconds=time.perf_counter() - started_at,
        )
        if temp_report is not None:
            temp_report.write_text(
                json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

        deduplicator.close()
        deduplicator = None
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
        if deduplicator is not None:
            deduplicator.close()
        for temporary in (temp_csv, temp_parquet, temp_report, temp_database):
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        raise
