from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq


PROJECT_ROOT = Path(__file__).resolve().parents[1]

SOURCE = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "user_behavior_clean.parquet"
)

OUTPUT = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "user_behavior_clean_sample.csv"
)

TARGET_ROWS = 10_000


def main():
    print(f"读取文件：{SOURCE}")

    if not SOURCE.exists():
        raise FileNotFoundError(f"找不到 parquet 文件：{SOURCE}")

    parquet_file = pq.ParquetFile(SOURCE)

    print(f"Parquet 总行数：{parquet_file.metadata.num_rows:,}")
    print(f"Row groups：{parquet_file.num_row_groups}")
    print(f"字段：{parquet_file.schema_arrow.names}")

    samples = []
    collected_rows = 0

    for batch in parquet_file.iter_batches(batch_size=10_000):
        df = batch.to_pandas()

        remaining = TARGET_ROWS - collected_rows
        take_rows = min(remaining, len(df))

        samples.append(df.iloc[:take_rows].copy())
        collected_rows += take_rows

        if collected_rows >= TARGET_ROWS:
            break

    if not samples:
        raise RuntimeError("没有从 parquet 中读取到任何数据。")

    sample_df = pd.concat(samples, ignore_index=True)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    sample_df.to_csv(
        OUTPUT,
        index=False,
        encoding="utf-8-sig",
    )

    print()
    print("样本生成成功！")
    print(f"输出路径：{OUTPUT}")
    print(f"样本行数：{len(sample_df):,}")
    print()
    print("字段类型：")
    print(sample_df.dtypes)
    print()
    print("前 5 行：")
    print(sample_df.head())


if __name__ == "__main__":
    main()
