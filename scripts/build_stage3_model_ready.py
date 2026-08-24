from pathlib import Path
import json
import math

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq


ROOT = Path("data/modeling")
CONFIG_PATH = Path("configs/stage3_feature_config.json")

SPLITS = ("train", "valid", "test")

CATEGORY_LEVELS = {
    "user_activity_level": ["low", "high"],
    "item_popularity_level": ["low", "medium", "high"],
    "category_popularity_level": ["long_tail", "medium", "popular"],
    "time_period": ["morning", "afternoon", "evening", "night"],
    "weekday": [0, 1, 2, 3, 4, 5, 6],
}

BATCH_SIZE = 200_000


def parse_sequence(value, length=10):
    if value is None or pd.isna(value):
        return [0] * length

    parts = str(value).split("|")

    seq = []
    for x in parts:
        x = x.strip()

        if x in {"1", "2", "3", "4"}:
            seq.append(int(x))

    seq = seq[-length:]

    if len(seq) < length:
        seq = [0] * (length - len(seq)) + seq

    return seq


def transform_batch(df, config):
    keys = df[config["key_columns"]].copy()
    label = df["label"].astype("uint8").copy()

    drop_columns = set(
        config["key_columns"]
        + config["metadata_columns"]
        + config["exclude_raw_columns"]
        + config["categorical_columns"]
        + [
            config["target_column"],
            config["sequence_column"],
        ]
    )

    feature_columns = [
        c for c in df.columns
        if c not in drop_columns
    ]

    X = df[feature_columns].copy()

    # -------------------------------------------------
    # Categorical one-hot encoding with fixed categories
    # -------------------------------------------------
    for col, levels in CATEGORY_LEVELS.items():
        for level in levels:
            out_col = f"{col}__{level}"

            if isinstance(level, int):
                X[out_col] = (
                    pd.to_numeric(df[col], errors="coerce")
                    .eq(level)
                    .astype("uint8")
                )
            else:
                X[out_col] = (
                    df[col]
                    .astype(str)
                    .eq(str(level))
                    .astype("uint8")
                )

    # -------------------------------------------------
    # Recent behavior sequence
    # -------------------------------------------------
    sequences = df[config["sequence_column"]].map(
        lambda x: parse_sequence(
            x,
            config["sequence_length"],
        )
    )

    seq_matrix = np.asarray(
        sequences.tolist(),
        dtype=np.uint8,
    )

    for i in range(config["sequence_length"]):
        X[f"seq_pos_{i + 1}"] = seq_matrix[:, i]

    for behavior in config["sequence_behavior_values"]:
        X[f"seq_count_behavior_{behavior}"] = (
            seq_matrix == behavior
        ).sum(axis=1).astype("uint8")

    X["seq_distinct_behavior_count"] = np.array(
        [
            len(set(row[row > 0]))
            for row in seq_matrix
        ],
        dtype=np.uint8,
    )

    # -------------------------------------------------
    # Cyclical hour transformation
    # -------------------------------------------------
    if "ui_last_interaction_hour" in X.columns:
        hour = pd.to_numeric(
            X["ui_last_interaction_hour"],
            errors="coerce",
        ).fillna(0)

        X["ui_last_interaction_hour_sin"] = np.sin(
            2 * math.pi * hour / 24.0
        )

        X["ui_last_interaction_hour_cos"] = np.cos(
            2 * math.pi * hour / 24.0
        )

        X = X.drop(columns=["ui_last_interaction_hour"])

    # -------------------------------------------------
    # Make sure all model features are numeric
    # -------------------------------------------------
    bad = [
        col
        for col in X.columns
        if not pd.api.types.is_numeric_dtype(X[col])
    ]

    if bad:
        raise RuntimeError(
            f"Non-numeric model features remain: {bad}"
        )

    result = pd.concat(
        [
            keys.reset_index(drop=True),
            X.reset_index(drop=True),
            label.rename("label").reset_index(drop=True),
        ],
        axis=1,
    )

    return result


def process_split(split, config):
    input_path = (
        ROOT
        / split
        / f"{split}_modeling.parquet"
    )

    output_path = (
        ROOT
        / split
        / f"{split}_model_ready.parquet"
    )

    pf = pq.ParquetFile(input_path)

    writer = None
    total_rows = 0
    expected_columns = None

    print("=" * 80)
    print("Processing:", split)
    print("Input     :", input_path)

    try:
        for batch_no, batch in enumerate(
            pf.iter_batches(batch_size=BATCH_SIZE),
            start=1,
        ):
            df = batch.to_pandas()

            transformed = transform_batch(
                df,
                config,
            )

            if expected_columns is None:
                expected_columns = transformed.columns.tolist()
            elif transformed.columns.tolist() != expected_columns:
                raise RuntimeError(
                    f"{split}: inconsistent columns between batches"
                )

            table = pa.Table.from_pandas(
                transformed,
                preserve_index=False,
            )

            if writer is None:
                writer = pq.ParquetWriter(
                    output_path,
                    table.schema,
                    compression="snappy",
                    use_dictionary=True,
                )

            writer.write_table(
                table,
                row_group_size=100_000,
            )

            total_rows += len(transformed)

            print(
                f"batch {batch_no:02d} | "
                f"rows processed = {total_rows:,}"
            )

    finally:
        if writer is not None:
            writer.close()

    print("Output    :", output_path)
    print("Rows      :", f"{total_rows:,}")
    print("Columns   :", len(expected_columns))

    return expected_columns


def main():
    config = json.loads(
        CONFIG_PATH.read_text(
            encoding="utf-8-sig"
        )
    )

    schemas = {}

    for split in SPLITS:
        schemas[split] = process_split(
            split,
            config,
        )

    reference = schemas["train"]

    print()
    print("=" * 80)
    print("FINAL SCHEMA CHECK")
    print("=" * 80)

    for split in SPLITS:
        same = schemas[split] == reference
        print(split, "same columns =", same)

        if not same:
            raise RuntimeError(
                f"{split}: model-ready schema mismatch"
            )

    feature_columns = [
        c
        for c in reference
        if c not in set(config["key_columns"]) | {"label"}
    ]

    feature_list_path = Path(
        "configs/stage3_model_feature_list.txt"
    )

    feature_list_path.write_text(
        "\n".join(feature_columns) + "\n",
        encoding="utf-8",
    )

    print()
    print("Model feature count:", len(feature_columns))
    print("Feature list saved :", feature_list_path)
    print("All preprocessing completed successfully.")


if __name__ == "__main__":
    main()
