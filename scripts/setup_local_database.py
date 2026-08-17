"""初始化本地 CSV、Parquet 和 SQLite 数据，并创建基础 SQL 对象。"""

from __future__ import annotations

import argparse
import sqlite3
import sys
import tempfile
import time
from contextlib import closing
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CSV_PATH = PROJECT_ROOT / "data" / "raw" / "user_behavior_processed.csv"
DEFAULT_DATABASE_PATH = PROJECT_ROOT / "database" / "taobao_user_behavior.db"
EXPECTED_CSV_NAME = "user_behavior_processed.csv"
TABLE_NAME = "user_behavior_processed"
EXPECTED_COLUMNS = [
    "time",
    "user_id",
    "item_id",
    "item_category",
    "behavior_type",
]
CSV_DTYPES = {
    "time": "string",
    "user_id": "Int64",
    "item_id": "Int64",
    "item_category": "Int64",
    "behavior_type": "Int64",
}
SQLITE_DTYPES = {
    "time": "TEXT",
    "user_id": "INTEGER",
    "item_id": "INTEGER",
    "item_category": "INTEGER",
    "behavior_type": "INTEGER",
}
INDEX_SQL_PATH = (
    PROJECT_ROOT / "sql" / "preprocessing" / "00_create_base_indexes.sql"
)
MAPPING_VIEW_SQL_PATH = (
    PROJECT_ROOT
    / "sql"
    / "preprocessing"
    / "01_create_behavior_mapping_view.sql"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "将淘宝用户行为 CSV 分块转换为 Parquet、导入 SQLite，"
            "并创建索引和标准映射视图。"
        )
    )
    parser.add_argument(
        "--csv",
        type=Path,
        default=DEFAULT_CSV_PATH,
        help=f"CSV 文件路径，默认：{DEFAULT_CSV_PATH}",
    )
    parser.add_argument(
        "--database",
        type=Path,
        default=DEFAULT_DATABASE_PATH,
        help=f"SQLite 数据库路径，默认：{DEFAULT_DATABASE_PATH}",
    )
    parser.add_argument(
        "--chunksize",
        type=int,
        default=100_000,
        help="每批处理行数，默认：100000",
    )
    parser.add_argument(
        "--encoding",
        default="utf-8-sig",
        help="CSV 文件编码，默认：utf-8-sig",
    )
    parser.add_argument(
        "--if-exists",
        choices=("skip", "fail", "replace", "append"),
        default="skip",
        help="SQLite 目标表已存在时的处理方式，默认：skip",
    )
    parser.add_argument(
        "--parquet-if-exists",
        choices=("skip", "fail", "replace"),
        default="skip",
        help="Parquet 已存在时的处理方式，默认：skip",
    )
    return parser.parse_args()


def resolve_path(path: Path) -> Path:
    return path if path.is_absolute() else (PROJECT_ROOT / path).resolve()


def validate_inputs(csv_path: Path, chunksize: int, encoding: str) -> None:
    if csv_path.name != EXPECTED_CSV_NAME:
        raise ValueError(
            f"原始 CSV 文件名必须为 {EXPECTED_CSV_NAME!r}，"
            f"当前为 {csv_path.name!r}"
        )
    if not csv_path.is_file():
        raise FileNotFoundError(f"未找到 CSV 文件：{csv_path}")
    if chunksize <= 0:
        raise ValueError("--chunksize 必须为正整数")
    for sql_path in (INDEX_SQL_PATH, MAPPING_VIEW_SQL_PATH):
        if not sql_path.is_file():
            raise FileNotFoundError(f"未找到 SQL 文件：{sql_path}")

    actual_columns = pd.read_csv(
        csv_path,
        encoding=encoding,
        nrows=0,
    ).columns.tolist()
    if actual_columns != EXPECTED_COLUMNS:
        raise ValueError(
            "CSV 字段不符合项目约定。"
            f"\n期望字段：{EXPECTED_COLUMNS}"
            f"\n实际字段：{actual_columns}"
        )


def table_exists(connection: sqlite3.Connection) -> bool:
    result = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (TABLE_NAME,),
    ).fetchone()
    return result is not None


def decide_database_write(
    connection: sqlite3.Connection,
    if_exists: str,
) -> tuple[bool, str]:
    exists = table_exists(connection)
    if not exists:
        return True, "fail"
    if if_exists == "fail":
        raise RuntimeError(
            f"目标表 {TABLE_NAME!r} 已存在。"
            "可使用 --if-exists skip、replace 或 append。"
        )
    if if_exists == "skip":
        return False, "skip"
    return True, if_exists


def decide_parquet_write(parquet_path: Path, if_exists: str) -> bool:
    if not parquet_path.exists():
        return True
    if if_exists == "fail":
        raise RuntimeError(
            f"Parquet 已存在：{parquet_path}。"
            "可使用 --parquet-if-exists skip 或 replace。"
        )
    return if_exists == "replace"


def create_temp_parquet_path(parquet_path: Path) -> Path:
    parquet_path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        prefix=f".{parquet_path.stem}.",
        suffix=".parquet.tmp",
        dir=parquet_path.parent,
        delete=False,
    )
    handle.close()
    return Path(handle.name)


def process_csv(
    connection: sqlite3.Connection,
    csv_path: Path,
    parquet_path: Path,
    chunksize: int,
    encoding: str,
    write_parquet: bool,
    write_database: bool,
    database_write_mode: str,
) -> tuple[int, int]:
    processed_rows = 0
    imported_rows = 0
    first_chunk = True
    parquet_writer: pq.ParquetWriter | None = None
    temp_parquet_path = (
        create_temp_parquet_path(parquet_path) if write_parquet else None
    )

    try:
        reader = pd.read_csv(
            csv_path,
            encoding=encoding,
            dtype=CSV_DTYPES,
            chunksize=chunksize,
        )
        for chunk_number, chunk in enumerate(reader, start=1):
            if write_parquet:
                arrow_table = pa.Table.from_pandas(
                    chunk,
                    preserve_index=False,
                )
                if parquet_writer is None:
                    parquet_writer = pq.ParquetWriter(
                        temp_parquet_path,
                        arrow_table.schema,
                        compression="snappy",
                    )
                parquet_writer.write_table(arrow_table)

            if write_database:
                write_mode = (
                    database_write_mode if first_chunk else "append"
                )
                chunk.to_sql(
                    TABLE_NAME,
                    connection,
                    if_exists=write_mode,
                    index=False,
                    dtype=SQLITE_DTYPES,
                )
                imported_rows += len(chunk)

            first_chunk = False
            processed_rows += len(chunk)
            print(
                f"已处理第 {chunk_number} 批，"
                f"本批 {len(chunk):,} 行，累计 {processed_rows:,} 行。"
            )

        if first_chunk:
            raise ValueError("CSV 文件只有表头，没有可处理的数据行")

        if parquet_writer is not None:
            parquet_writer.close()
            parquet_writer = None
        if write_parquet and temp_parquet_path is not None:
            temp_parquet_path.replace(parquet_path)
    except Exception:
        if parquet_writer is not None:
            parquet_writer.close()
        if temp_parquet_path is not None:
            temp_parquet_path.unlink(missing_ok=True)
        raise

    return processed_rows, imported_rows


def parquet_info(parquet_path: Path) -> tuple[int, list[str]]:
    parquet_file = pq.ParquetFile(parquet_path)
    try:
        return parquet_file.metadata.num_rows, parquet_file.schema_arrow.names
    finally:
        parquet_file.close()


def execute_sql_file(
    connection: sqlite3.Connection,
    sql_path: Path,
    description: str,
) -> None:
    print(f"正在{description}：{sql_path.relative_to(PROJECT_ROOT)}")
    connection.executescript(sql_path.read_text(encoding="utf-8"))


def verify_database(connection: sqlite3.Connection) -> tuple[int, bool]:
    total_rows = connection.execute(
        f"SELECT COUNT(*) FROM {TABLE_NAME}"
    ).fetchone()[0]
    view_exists = (
        connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'view' AND name = ?",
            ("vw_user_behavior_mapped",),
        ).fetchone()
        is not None
    )
    return total_rows, view_exists


def main() -> int:
    args = parse_args()
    csv_path = resolve_path(args.csv)
    parquet_path = csv_path.with_suffix(".parquet")
    database_path = resolve_path(args.database)

    try:
        validate_inputs(csv_path, args.chunksize, args.encoding)
        database_path.parent.mkdir(parents=True, exist_ok=True)

        print(f"CSV 路径：{csv_path}")
        print(f"Parquet 路径：{parquet_path}")
        print(f"数据库路径：{database_path}")
        print(f"SQLite 目标表：{TABLE_NAME}")
        started_at = time.perf_counter()

        with closing(sqlite3.connect(database_path, timeout=60)) as connection:
            connection.execute("PRAGMA synchronous = NORMAL")
            connection.execute("PRAGMA temp_store = MEMORY")

            write_parquet = decide_parquet_write(
                parquet_path,
                args.parquet_if_exists,
            )
            write_database, database_write_mode = decide_database_write(
                connection,
                args.if_exists,
            )

            if write_parquet or write_database:
                processed_rows, imported_rows = process_csv(
                    connection=connection,
                    csv_path=csv_path,
                    parquet_path=parquet_path,
                    chunksize=args.chunksize,
                    encoding=args.encoding,
                    write_parquet=write_parquet,
                    write_database=write_database,
                    database_write_mode=database_write_mode,
                )
            else:
                processed_rows = 0
                imported_rows = 0
                print("Parquet 和 SQLite 原始表均已存在，跳过数据转换与导入。")

            execute_sql_file(connection, INDEX_SQL_PATH, "创建基础索引")
            execute_sql_file(
                connection,
                MAPPING_VIEW_SQL_PATH,
                "创建标准行为映射视图",
            )
            database_rows, view_exists = verify_database(connection)

        parquet_rows, parquet_columns = parquet_info(parquet_path)
        if parquet_columns != EXPECTED_COLUMNS:
            raise ValueError(
                "Parquet 字段不符合项目约定。"
                f"\n期望字段：{EXPECTED_COLUMNS}"
                f"\n实际字段：{parquet_columns}"
            )
        if write_parquet and parquet_rows != processed_rows:
            raise RuntimeError(
                "Parquet 行数与本次处理行数不一致："
                f"{parquet_rows:,} != {processed_rows:,}"
            )
        elapsed = time.perf_counter() - started_at

        parquet_status = "是（新生成）" if write_parquet else "是（复用已有文件）"
        print("本地数据初始化完成。")
        print(f"CSV 路径：{csv_path}")
        print(f"Parquet 路径：{parquet_path}")
        print(f"Parquet 总行数：{parquet_rows:,}")
        print(f"Parquet 字段名：{', '.join(parquet_columns)}")
        print(f"Parquet 转换是否成功：{parquet_status}")
        print(f"本次导入 SQLite：{imported_rows:,} 行")
        print(f"SQLite 原始表总行数：{database_rows:,}")
        print(f"映射视图已创建：{'是' if view_exists else '否'}")
        print(f"总耗时：{elapsed:.1f} 秒")
        return 0
    except Exception as error:
        print(f"初始化失败：{error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
