"""Build fixed-window Stage 3 purchase labels."""

from pathlib import Path

import pandas as pd


INPUT_PATH = Path("data/processed/user_behavior_clean.parquet")
OUTPUT_DIR = Path("data/modeling")

SPLIT_WINDOWS = {
    "train": {
        "feature_start": pd.Timestamp("2025-11-18"),
        "feature_end": pd.Timestamp("2025-12-07"),
        "label_date": pd.Timestamp("2025-12-08"),
    },
    "valid": {
        "feature_start": pd.Timestamp("2025-12-09"),
        "feature_end": pd.Timestamp("2025-12-14"),
        "label_date": pd.Timestamp("2025-12-15"),
    },
    "test": {
        "feature_start": pd.Timestamp("2025-12-16"),
        "feature_end": pd.Timestamp("2025-12-17"),
        "label_date": pd.Timestamp("2025-12-18"),
    },
}


def build_split(
    df: pd.DataFrame,
    split_name: str,
    feature_start: pd.Timestamp,
    feature_end: pd.Timestamp,
    label_date: pd.Timestamp,
) -> pd.DataFrame:
    """Build candidates from one fixed feature window and label one day."""
    feature_start = pd.Timestamp(feature_start).normalize()
    feature_end = pd.Timestamp(feature_end).normalize()
    label_date = pd.Timestamp(label_date).normalize()

    feature_end_exclusive = feature_end + pd.Timedelta(days=1)
    label_end_exclusive = label_date + pd.Timedelta(days=1)

    if feature_end_exclusive != label_date:
        raise ValueError(
            f"{split_name}: label_date must immediately follow feature_end"
        )

    history = df[
        (df["time"] >= feature_start)
        & (df["time"] < feature_end_exclusive)
    ]
    candidates = (
        history[["user_id", "item_id"]]
        .drop_duplicates()
        .reset_index(drop=True)
    )

    purchases = (
        df[
            (df["time"] >= label_date)
            & (df["time"] < label_end_exclusive)
            & (df["behavior_type"] == 4)
        ][["user_id", "item_id"]]
        .drop_duplicates()
        .assign(label=1)
    )

    labels = candidates.merge(
        purchases,
        on=["user_id", "item_id"],
        how="left",
        validate="one_to_one",
    )
    labels["label"] = labels["label"].fillna(0).astype("uint8")

    # Keep the existing field name for downstream compatibility. In this
    # fixed-snapshot design it records the single label day for the split.
    labels["prediction_date"] = label_date
    labels["cutoff_time"] = feature_end_exclusive - pd.Timedelta(seconds=1)
    labels["label_start"] = label_date
    labels["label_end"] = label_end_exclusive - pd.Timedelta(seconds=1)

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
    ].sort_values(["user_id", "item_id"]).reset_index(drop=True)

    duplicate_keys = int(
        labels.duplicated(["user_id", "item_id", "prediction_date"]).sum()
    )
    if duplicate_keys:
        raise RuntimeError(
            f"{split_name}: duplicate user_id + item_id + prediction_date "
            f"keys: {duplicate_keys:,}"
        )

    return labels


def main() -> None:
    print("Loading clean behavior data...")
    df = pd.read_parquet(
        INPUT_PATH,
        columns=["time", "user_id", "item_id", "behavior_type"],
    )
    df["time"] = pd.to_datetime(df["time"])
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    summary_rows = []
    combined_results = []

    for split_name, window in SPLIT_WINDOWS.items():
        result = build_split(df, split_name, **window)
        output_path = OUTPUT_DIR / f"{split_name}_labels.parquet"
        result.to_parquet(output_path, index=False)
        combined_result = result[
            ["user_id", "item_id", "prediction_date", "label"]
        ].copy()
        combined_result.insert(3, "dataset", split_name)
        combined_results.append(combined_result)

        positives = int(result["label"].sum())
        label_start = window["label_date"].normalize()
        label_end = label_start + pd.Timedelta(days=1)
        label_purchase_pairs = (
            df[
                (df["time"] >= label_start)
                & (df["time"] < label_end)
                & (df["behavior_type"] == 4)
            ][["user_id", "item_id"]]
            .drop_duplicates()
        )
        candidate_pairs = result[["user_id", "item_id"]]
        excluded_purchase_pairs = len(
            label_purchase_pairs.merge(
                candidate_pairs,
                on=["user_id", "item_id"],
                how="left",
                indicator=True,
            ).query("_merge == 'left_only'")
        )
        summary_rows.append(
            {
                "dataset": split_name,
                "feature_start": window["feature_start"].date(),
                "feature_end": window["feature_end"].date(),
                "label_start": window["label_date"].date(),
                "label_end": window["label_date"].date(),
                "total_samples": len(result),
                "positive_samples": positives,
                "negative_samples": len(result) - positives,
                "positive_rate": positives / len(result),
                "label_purchase_pairs": len(label_purchase_pairs),
                "excluded_new_purchase_pairs": excluded_purchase_pairs,
            }
        )
        print(
            f"{split_name}: features "
            f"{window['feature_start'].date()}~{window['feature_end'].date()}, "
            f"label {window['label_date'].date()}, rows={len(result):,}, "
            f"positive={positives:,}, "
            f"rate={positives / len(result):.6%} -> {output_path}"
        )

    combined_path = OUTPUT_DIR / "purchase_labels.parquet"
    pd.concat(combined_results, ignore_index=True).to_parquet(
        combined_path,
        index=False,
    )
    summary_path = OUTPUT_DIR / "purchase_label_summary.csv"
    pd.DataFrame(summary_rows).to_csv(summary_path, index=False)
    print(f"combined labels -> {combined_path}")
    print(f"summary -> {summary_path}")


if __name__ == "__main__":
    main()
