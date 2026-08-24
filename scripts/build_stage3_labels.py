from pathlib import Path
import pandas as pd

INPUT_PATH = Path("data/processed/user_behavior_clean.parquet")
OUTPUT_DIR = Path("data/modeling")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

SPLIT_DATE_RANGES = {
    "train": (
        pd.Timestamp("2025-11-18"),
        pd.Timestamp("2025-12-07"),
    ),
    "valid": (
        pd.Timestamp("2025-12-08"),
        pd.Timestamp("2025-12-14"),
    ),
    "test": (
        pd.Timestamp("2025-12-15"),
        pd.Timestamp("2025-12-17"),
    ),
}


def build_one_prediction_date(df, prediction_date):
    prediction_date = pd.Timestamp(prediction_date).normalize()

    cutoff_time = (
        prediction_date
        + pd.Timedelta(days=1)
        - pd.Timedelta(seconds=1)
    )

    label_start = prediction_date + pd.Timedelta(days=1)
    label_end = label_start + pd.Timedelta(days=1)

    # 只允许使用 prediction_date 当天及以前的历史行为
    history = df[df["time"] <= cutoff_time]

    candidates = (
        history[["user_id", "item_id"]]
        .drop_duplicates()
        .reset_index(drop=True)
    )

    # 下一自然日是否购买该商品
    next_day_buy = (
        df[
            (df["time"] >= label_start)
            & (df["time"] < label_end)
            & (df["behavior_type"] == 4)
        ][["user_id", "item_id"]]
        .drop_duplicates()
        .reset_index(drop=True)
    )

    next_day_buy["label"] = 1

    labels = candidates.merge(
        next_day_buy,
        on=["user_id", "item_id"],
        how="left",
    )

    labels["label"] = (
        labels["label"]
        .fillna(0)
        .astype("uint8")
    )

    labels["prediction_date"] = prediction_date
    labels["cutoff_time"] = cutoff_time
    labels["label_start"] = label_start
    labels["label_end"] = (
        label_end - pd.Timedelta(seconds=1)
    )

    labels = labels[
        [
            "user_id",
            "item_id",
            "prediction_date",
            "cutoff_time",
            "label_start",
            "label_end",
            "label",
        ]
    ]

    return labels


def build_split(df, split_name, start_date, end_date):
    print("=" * 80)
    print(f"split: {split_name}")
    print(
        "prediction dates:",
        start_date.date(),
        "~",
        end_date.date(),
    )
    print("=" * 80)

    parts = []

    dates = pd.date_range(
        start=start_date,
        end=end_date,
        freq="D",
    )

    for prediction_date in dates:
        part = build_one_prediction_date(
            df,
            prediction_date,
        )

        positives = int(part["label"].sum())
        positive_rate = (
            positives / len(part)
            if len(part)
            else 0.0
        )

        print(
            f"{prediction_date.date()} "
            f"| rows={len(part):,} "
            f"| positive={positives:,} "
            f"| rate={positive_rate:.6%}"
        )

        parts.append(part)

    result = pd.concat(
        parts,
        ignore_index=True,
    )

    duplicate_keys = int(
        result.duplicated(
            [
                "user_id",
                "item_id",
                "prediction_date",
            ]
        ).sum()
    )

    if duplicate_keys:
        raise RuntimeError(
            f"{split_name}: duplicate "
            f"user_id + item_id + prediction_date keys: "
            f"{duplicate_keys:,}"
        )

    output_path = (
        OUTPUT_DIR
        / f"{split_name}_labels.parquet"
    )

    result.to_parquet(
        output_path,
        index=False,
    )

    positives = int(result["label"].sum())

    print()
    print(f"{split_name} rows       : {len(result):,}")
    print(f"{split_name} positive   : {positives:,}")
    print(
        f"{split_name} positive rate: "
        f"{positives / len(result):.6%}"
    )
    print(f"saved to: {output_path}")
    print()


def main():
    print("Loading clean behavior data...")

    df = pd.read_parquet(
        INPUT_PATH,
        columns=[
            "time",
            "user_id",
            "item_id",
            "behavior_type",
        ],
    )

    df["time"] = pd.to_datetime(df["time"])

    print(
        "time range:",
        df["time"].min(),
        "~",
        df["time"].max(),
    )
    print(f"rows: {len(df):,}")
    print()

    for split_name, (
        start_date,
        end_date,
    ) in SPLIT_DATE_RANGES.items():
        build_split(
            df,
            split_name,
            start_date,
            end_date,
        )


if __name__ == "__main__":
    main()
