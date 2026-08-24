from pathlib import Path
import pandas as pd

INPUT_PATH = Path("data/processed/user_behavior_clean.parquet")
OUTPUT_DIR = Path("data/modeling")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

CUTOFFS = {
    "train": pd.Timestamp("2025-11-27 23:59:59"),
    "valid": pd.Timestamp("2025-12-04 23:59:59"),
    "test": pd.Timestamp("2025-12-11 23:59:59"),
}

LABEL_DAYS = 7


def build_labels(df, split_name, cutoff):
    label_start = cutoff.normalize() + pd.Timedelta(days=1)
    label_end = label_start + pd.Timedelta(days=LABEL_DAYS)

    history = df[df["time"] <= cutoff]

    candidates = (
        history[["user_id", "item_id"]]
        .drop_duplicates()
        .reset_index(drop=True)
    )

    future_buy_all = (
        df[
            (df["time"] >= label_start)
            & (df["time"] < label_end)
            & (df["behavior_type"] == 4)
        ][["user_id", "item_id"]]
        .drop_duplicates()
        .reset_index(drop=True)
    )

    covered_future_buy = future_buy_all.merge(
        candidates,
        on=["user_id", "item_id"],
        how="inner",
    )

    unseen_future_buy = len(future_buy_all) - len(covered_future_buy)

    future_buy = covered_future_buy.copy()
    future_buy["label"] = 1

    labels = candidates.merge(
        future_buy,
        on=["user_id", "item_id"],
        how="left",
    )

    labels["label"] = labels["label"].fillna(0).astype("uint8")
    labels["cutoff_time"] = cutoff
    labels["label_start"] = label_start
    labels["label_end"] = label_end - pd.Timedelta(seconds=1)

    output_path = OUTPUT_DIR / f"{split_name}_labels.parquet"
    labels.to_parquet(output_path, index=False)

    n = len(labels)
    positives = int(labels["label"].sum())
    negatives = n - positives
    positive_rate = positives / n if n else 0

    total_future_buy = len(future_buy_all)
    coverage = positives / total_future_buy if total_future_buy else 0

    print("=" * 70)
    print(f"split                    : {split_name}")
    print(f"cutoff                   : {cutoff}")
    print(f"label window             : {label_start} ~ {label_end - pd.Timedelta(seconds=1)}")
    print(f"candidate samples        : {n:,}")
    print(f"positive                 : {positives:,}")
    print(f"negative                 : {negatives:,}")
    print(f"positive rate            : {positive_rate:.6%}")
    print(f"all future buy pairs     : {total_future_buy:,}")
    print(f"covered future buy pairs : {positives:,}")
    print(f"unseen future buy pairs  : {unseen_future_buy:,}")
    print(f"candidate coverage       : {coverage:.6%}")
    print(f"saved to                 : {output_path}")


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

    print(f"rows: {len(df):,}")
    print(f"time range: {df['time'].min()} ~ {df['time'].max()}")

    for split_name, cutoff in CUTOFFS.items():
        build_labels(df, split_name, cutoff)


if __name__ == "__main__":
    main()
