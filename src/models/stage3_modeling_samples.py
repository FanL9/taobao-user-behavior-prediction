import numpy as np
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from src.features.conversion_features import (
    build_item_conversion_features,
)


ROOT: Path = Path("data/splits")

SPLIT_DATE_RANGES = {
    "train": (
        pd.Timestamp("2025-12-08"),
        pd.Timestamp("2025-12-08"),
    ),
    "valid": (
        pd.Timestamp("2025-12-15"),
        pd.Timestamp("2025-12-15"),
    ),
    "test": (
        pd.Timestamp("2025-12-18"),
        pd.Timestamp("2025-12-18"),
    ),
}


def load_labels(split):
    path = ROOT / f"{split}_labels.parquet"

    labels = pd.read_parquet(path)

    labels["prediction_date"] = pd.to_datetime(
        labels["prediction_date"]
    ).dt.normalize()

    return labels


def build_one_snapshot(
    split,
    prediction_date,
    labels_for_date,
):

    date_string = prediction_date.strftime("%Y-%m-%d")

    feature_dir = (
        ROOT
        / split
        / "snapshots"
        / date_string
        / "features"
    )

    user_item = pq.read_table(
        feature_dir / "user_item_features.parquet"
    ).to_pandas()

    user = pq.read_table(
        feature_dir / "user_features.parquet"
    ).to_pandas()

    item_arrow = pq.read_table(
        feature_dir / "item_features.parquet"
    )

    item = item_arrow.to_pandas()

    category = pq.read_table(
        feature_dir / "category_features.parquet"
    ).to_pandas()

    time = pq.read_table(
        feature_dir / "time_features.parquet"
    ).to_pandas()

    sequence = pq.read_table(
        feature_dir / "user_sequence_features.parquet"
    ).to_pandas()

    conversion = (
        build_item_conversion_features(
            item_arrow
        )
        .to_pandas()
    )

    base = labels_for_date.copy()

    base = base.merge(
        user_item,
        on=["user_id", "item_id"],
        how="left",
        validate="one_to_one",
    )

    base = base.merge(
        user,
        on="user_id",
        how="left",
        validate="many_to_one",
    )

    base = base.merge(
        sequence,
        on="user_id",
        how="left",
        validate="many_to_one",
    )

    base = base.merge(
        item,
        on="item_id",
        how="left",
        validate="many_to_one",
    )

    base = base.merge(
        category,
        on="category_id",
        how="left",
        validate="many_to_one",
    )

    if "ui_last_interaction_date" in base.columns:
        base["ui_last_interaction_date"] = pd.to_datetime(
            base["ui_last_interaction_date"]
        ).dt.date

    if "behavior_date" in time.columns:
        time["behavior_date"] = pd.to_datetime(
            time["behavior_date"]
        ).dt.date

    base = base.merge(
        time,
        left_on=[
            "ui_last_interaction_date",
            "ui_last_interaction_hour",
        ],
        right_on=[
            "behavior_date",
            "behavior_hour",
        ],
        how="left",
        validate="many_to_one",
    )

    base = base.merge(
        conversion,
        on="item_id",
        how="left",
        validate="many_to_one",
    )

    base["prediction_date"] = prediction_date

    if "behavior_date" in base.columns:
        base = base.drop(
            columns=["behavior_date"]
        )

    if "behavior_hour" in base.columns:
        base = base.drop(
            columns=["behavior_hour"]
        )

    seq_col = "sequence_recent_10_behavior_types"

    if seq_col in base.columns:
        base[seq_col] = base[seq_col].map(
            lambda values: (
                "|".join(
                    str(int(v))
                    for v in values
                )
                if isinstance(values, (list, tuple, np.ndarray))
                else ""
            )
        )

    protected = {
        "user_id",
        "item_id",
        "prediction_date",
        "cutoff_time",
        "label_start",
        "label_end",
        "label",
    }

    feature_cols = [
        c
        for c in base.columns
        if c not in protected
    ]

    null_cols = [
        c
        for c in feature_cols
        if base[c].isna().any()
    ]

    if null_cols:
        raise RuntimeError(
            f"{split} {date_string}: "
            f"null features after joins: "
            f"{null_cols}"
        )

    duplicate_count = int(
        base.duplicated(
            [
                "user_id",
                "item_id",
                "prediction_date",
            ]
        ).sum()
    )

    if duplicate_count:
        raise RuntimeError(
            f"{split} {date_string}: "
            f"duplicate modeling keys = "
            f"{duplicate_count:,}"
        )

    return base


def build_split(split, start_date, end_date):

    print("=" * 80)
    print("Building modeling split:", split)
    print("=" * 80)

    labels = load_labels(split)

    output_path = (
        ROOT
        / split
        / f"{split}_modeling.parquet"
    )

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    writer = None
    expected_schema = None

    total_rows = 0
    total_positive = 0

    try:
        for prediction_date in pd.date_range(
            start=start_date,
            end=end_date,
            freq="D",
        ):

            labels_for_date = labels[
                labels["prediction_date"]
                == prediction_date.normalize()
            ].copy()

            if labels_for_date.empty:
                raise RuntimeError(
                    f"{split}: no labels for "
                    f"{prediction_date.date()}"
                )

            part = build_one_snapshot(
                split,
                prediction_date,
                labels_for_date,
            )

            part = part.sort_values(
                [
                    "user_id",
                    "item_id",
                ]
            ).reset_index(drop=True)

            table = pa.Table.from_pandas(
                part,
                preserve_index=False,
            )

            if expected_schema is None:
                expected_schema = table.schema

                writer = pq.ParquetWriter(
                    output_path,
                    expected_schema,
                    compression="snappy",
                    use_dictionary=True,
                )

            elif table.schema != expected_schema:
                raise RuntimeError(
                    f"{split} {prediction_date.date()}: "
                    "schema mismatch between snapshots"
                )

            writer.write_table(
                table,
                row_group_size=100_000,
            )

            rows = len(part)
            positives = int(part["label"].sum())

            total_rows += rows
            total_positive += positives

            print(
                f"{prediction_date.date()} "
                f"| rows={rows:,} "
                f"| positive={positives:,} "
                f"| cumulative={total_rows:,}"
            )

            del part
            del table
            del labels_for_date

    finally:
        if writer is not None:
            writer.close()

    print()
    print("saved :", output_path)
    print("rows  :", f"{total_rows:,}")
    print(
        "positive rate:",
        f"{total_positive / total_rows:.6%}",
    )
    print()


def main():

    for split, (
        start_date,
        end_date,
    ) in SPLIT_DATE_RANGES.items():

        build_split(
            split,
            start_date,
            end_date,
        )


if __name__ == "__main__":
    main()

