from pathlib import Path
import json
import time

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq


INPUT_PATH = Path("data/processed/user_behavior_clean.parquet")
OUTPUT_PATH = Path("data/features/user_sequence_features.parquet")


def build_user_sequence_features():
    start = time.time()

    print("Reading:", INPUT_PATH)

    df = pd.read_parquet(
        INPUT_PATH,
        columns=[
            "user_id",
            "item_id",
            "behavior_type",
            "time",
        ],
    )

    print("input rows =", len(df))
    print("users      =", df["user_id"].nunique())

    df = df.sort_values(
        ["user_id", "time", "item_id", "behavior_type"],
        kind="mergesort",
    ).reset_index(drop=True)

    # ---------------------------------------------------------
    # 1. Recent 10 behavior types
    # ---------------------------------------------------------
    recent = (
        df.groupby("user_id", sort=False)["behavior_type"]
        .agg(lambda s: list(s.tail(10).astype(int)))
        .rename("sequence_recent_10_behavior_types")
    )

    # ---------------------------------------------------------
    # 2. Average behavior gap in hours
    # Approximate because source timestamps are hour-level only.
    # ---------------------------------------------------------
    gaps = (
        df.groupby("user_id", sort=False)["time"]
        .apply(
            lambda s: (
                s.diff()
                .dt.total_seconds()
                .div(3600.0)
                .dropna()
                .mean()
            )
        )
        .fillna(0.0)
        .rename("sequence_avg_behavior_gap_hours")
    )

    # ---------------------------------------------------------
    # 3. User-item behavior-chain flags
    #
    # Evaluate whether a valid chain ever exists for the same
    # user-item pair. Source timestamps have hour-level precision,
    # so behavior_type is used as the deterministic tie breaker.
    # ---------------------------------------------------------
    chain_df = df.sort_values(
        ["user_id", "item_id", "time", "behavior_type"],
        kind="mergesort",
    ).reset_index(drop=True)

    group_keys = [
        chain_df["user_id"],
        chain_df["item_id"],
    ]

    behavior = chain_df["behavior_type"]

    # Has a PV occurred at or before the current row?
    seen_pv = (
        behavior.eq(1)
        .groupby(group_keys, sort=False)
        .cummax()
    )

    valid_pv_cart = behavior.eq(3) & seen_pv
    valid_pv_fav = behavior.eq(2) & seen_pv
    valid_pv_buy = behavior.eq(4) & seen_pv

    # A complete PV -> Cart -> Buy chain requires a valid
    # PV -> Cart to have occurred before or at the Buy row.
    seen_valid_cart = (
        valid_pv_cart
        .groupby(group_keys, sort=False)
        .cummax()
    )

    valid_pv_cart_buy = (
        behavior.eq(4)
        & seen_valid_cart
    )

    chain_df["sequence_has_pv_cart"] = valid_pv_cart.astype("uint8")
    chain_df["sequence_has_pv_fav"] = valid_pv_fav.astype("uint8")
    chain_df["sequence_has_pv_buy"] = valid_pv_buy.astype("uint8")
    chain_df["sequence_has_pv_cart_buy"] = (
        valid_pv_cart_buy.astype("uint8")
    )

    chain_cols = [
        "sequence_has_pv_cart",
        "sequence_has_pv_fav",
        "sequence_has_pv_buy",
        "sequence_has_pv_cart_buy",
    ]

    # Collapse all qualifying user-item chains to user-level flags.
    user_chain = (
        chain_df.groupby("user_id", sort=False)[chain_cols]
        .max()
        .astype("uint8")
    )

    # ---------------------------------------------------------
    # 4. Merge to one row per user
    # ---------------------------------------------------------
    result = pd.concat(
        [recent, gaps, user_chain],
        axis=1,
    ).reset_index()

    result["user_id"] = result["user_id"].astype("int64")
    result["sequence_avg_behavior_gap_hours"] = (
        result["sequence_avg_behavior_gap_hours"]
        .astype("float64")
    )

    for col in chain_cols:
        result[col] = result[col].fillna(0).astype("uint8")

    result = result.sort_values("user_id").reset_index(drop=True)

    # ---------------------------------------------------------
    # 5. Basic validation
    # ---------------------------------------------------------
    if result["user_id"].isna().any():
        raise ValueError("user_id contains null")

    if result["user_id"].duplicated().any():
        raise ValueError("duplicate user_id found")

    invalid_recent = result["sequence_recent_10_behavior_types"].apply(
        lambda x: (
            not isinstance(x, list)
            or len(x) > 10
            or any(v not in (1, 2, 3, 4) for v in x)
        )
    )

    if invalid_recent.any():
        raise ValueError("invalid recent behavior sequence found")

    for col in chain_cols:
        if not result[col].isin([0, 1]).all():
            raise ValueError(f"{col} contains values other than 0/1")

    # ---------------------------------------------------------
    # 6. Explicit Arrow schema
    # ---------------------------------------------------------
    schema = pa.schema(
        [
            ("user_id", pa.int64()),
            (
                "sequence_recent_10_behavior_types",
                pa.list_(pa.int64()),
            ),
            (
                "sequence_avg_behavior_gap_hours",
                pa.float64(),
            ),
            ("sequence_has_pv_cart", pa.uint8()),
            ("sequence_has_pv_fav", pa.uint8()),
            ("sequence_has_pv_buy", pa.uint8()),
            ("sequence_has_pv_cart_buy", pa.uint8()),
        ]
    )

    table = pa.Table.from_pandas(
        result,
        schema=schema,
        preserve_index=False,
    )

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    pq.write_table(
        table,
        OUTPUT_PATH,
        compression="snappy",
    )

    elapsed = round(time.time() - start, 3)

    summary = {
        "input": str(INPUT_PATH.resolve()),
        "input_rows": int(len(df)),
        "users": int(result["user_id"].nunique()),
        "output": str(OUTPUT_PATH.resolve()),
        "output_rows": int(len(result)),
        "columns": result.columns.tolist(),
        "elapsed_seconds": elapsed,
    }

    print(json.dumps(summary, ensure_ascii=False, indent=2))

    return summary


if __name__ == "__main__":
    build_user_sequence_features()
