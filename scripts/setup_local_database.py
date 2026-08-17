"""将项目 CSV 导入 SQLite，并创建基础索引和标准行为映射视图。"""

from __future__ import annotations

import argparse
import sqlite3
import sys
import time
from contextlib import closing
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CSV_PATH = PROJECT_ROOT / "data" / "raw" / "user_behavior_processed.csv"
DEFAULT_DATABASE_PATH = PROJECT_ROOT / "database" / "taobao_user_behavior.db"
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
        description="导入淘宝用户行为 CSV，并自动创建索引和标准映射视图。"
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
        help="每批导入行数，默认：100000",
    )
    parser.add_argument(
        "--encoding",
        default="utf-8-sig",
        help="CSV 文件编码，默认：utf-8-sig",
    )
    parser.add_argument(
        "--if-exists",
        choices=("fail", "replace", "append"),
        default="fail",
        help="目标表已存在时的处理方式，默认：fail",
    )
    return parser.parse_args()


def resolve_path(path: Path) -> Path:
    return path if path.is_absolute() else (PROJECT_ROOT / path).resolve()


def validate_inputs(csv_path: Path, chunksize: int, encoding: str) -> None:
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


def import_csv(
    connection: sqlite3.Connection,
    csv_path: Path,
    chunksize: int,
    encoding: str,
    if_exists: str,
) -> int:
    if if_exists == "fail" and table_exists(connection):
        raise RuntimeError(
            f"目标表 {TABLE_NAME!r} 已存在。"
            "如需重建，请显式使用 --if-exists replace；"
            "如需追加，请使用 --if-exists append。"
        )

    imported_rows = 0
    first_chunk = True
    reader = pd.read_csv(
        csv_path,
        encoding=encoding,
        dtype=CSV_DTYPES,
        chunksize=chunksize,
    )

    for chunk_number, chunk in enumerate(reader, start=1):
        write_mode = if_exists if first_chunk else "append"
        chunk.to_sql(
            TABLE_NAME,
            connection,
            if_exists=write_mode,
            index=False,
            dtype=SQLITE_DTYPES,
        )
        first_chunk = False
        imported_rows += len(chunk)
        print(
            f"已导入第 {chunk_number} 批，"
            f"本批 {len(chunk):,} 行，累计 {imported_rows:,} 行。"
        )

    if first_chunk:
        raise ValueError("CSV 文件只有表头，没有可导入的数据行")

    return imported_rows


def execute_sql_file(
    connection: sqlite3.Connection,
    sql_path: Path,
    description: str,
) -> None:
    print(f"正在{description}：{sql_path.relative_to(PROJECT_ROOT)}")
    connection.executescript(sql_path.read_text(encoding="utf-8"))


def verify_result(connection: sqlite3.Connection) -> tuple[int, bool]:
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
    database_path = resolve_path(args.database)

    try:
        validate_inputs(csv_path, args.chunksize, args.encoding)
        database_path.parent.mkdir(parents=True, exist_ok=True)

        print(f"CSV：{csv_path}")
        print(f"数据库：{database_path}")
        print(f"目标表：{TABLE_NAME}")
        started_at = time.perf_counter()

        with closing(sqlite3.connect(database_path, timeout=60)) as connection:
            connection.execute("PRAGMA synchronous = NORMAL")
            connection.execute("PRAGMA temp_store = MEMORY")

            imported_rows = import_csv(
                connection=connection,
                csv_path=csv_path,
                chunksize=args.chunksize,
                encoding=args.encoding,
                if_exists=args.if_exists,
            )
            execute_sql_file(connection, INDEX_SQL_PATH, "创建基础索引")
            execute_sql_file(
                connection,
                MAPPING_VIEW_SQL_PATH,
                "创建标准行为映射视图",
            )
            total_rows, view_exists = verify_result(connection)

        elapsed = time.perf_counter() - started_at
        print("本地数据库初始化完成。")
        print(f"本次导入：{imported_rows:,} 行")
        print(f"目标表总行数：{total_rows:,}")
        print(f"映射视图已创建：{'是' if view_exists else '否'}")
        print(f"耗时：{elapsed:.1f} 秒")
        return 0
    except Exception as error:
        print(f"初始化失败：{error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
