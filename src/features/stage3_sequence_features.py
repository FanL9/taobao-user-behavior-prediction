from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq


INPUT_PATH: Path = Path(
    "data/processed/user_behavior_clean.parquet"
)

SPLIT_WINDOWS = {
    "train": (
        pd.Timestamp("2025-11-18"),
        pd.Timestamp("2025-12-07"),
        pd.Timestamp("2025-12-08"),
    ),
    "valid": (
        pd.Timestamp("2025-12-09"),
        pd.Timestamp("2025-12-14"),
        pd.Timestamp("2025-12-15"),
    ),
    "test": (
        pd.Timestamp("2025-12-16"),
        pd.Timestamp("2025-12-17"),
        pd.Timestamp("2025-12-18"),
    ),
}


def build_one(split_name, observation_start, observation_end, label_date):

    cutoff = (
        observation_end.normalize()
        + pd.Timedelta(days=1)
        - pd.Timedelta(seconds=1)
    )

    print("=" * 80)
    print("split           :", split_name)
    print("label_date      :", label_date.date())
    print("observation_from:", observation_start.date())
    print("cutoff          :", cutoff)

    df = pd.read_parquet(
        INPUT_PATH,
        columns=[
            "user_id",
            "item_id",
            "behavior_type",
            "time",
        ],
        filters=[
            ("time", ">=", observation_start),
            ("time", "<=", cutoff),
        ],
    )

    print("input rows:", f"{len(df):,}")

    df = df.sort_values(
        [
            "user_id",
            "time",
            "item_id",
            "behavior_type",
        ],
        kind="mergesort",
    ).reset_index(drop=True)

    recent = (
        df.groupby(
            "user_id",
            sort=False,
        )["behavior_type"]
        .agg(
            lambda s: list(
                s.tail(10).astype(int)
            )
        )
        .rename(
            "sequence_recent_10_behavior_types"
        )
    )

    gaps = (
        df.groupby(
            "user_id",
            sort=False,
        )["time"]
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
        .rename(
            "sequence_avg_behavior_gap_hours"
        )
    )

    chain_df = df.sort_values(
        [
            "user_id",
            "item_id",
            "time",
            "behavior_type",
        ],
        kind="mergesort",
    ).reset_index(drop=True)

    group_keys = [
        chain_df["user_id"],
        chain_df["item_id"],
    ]

    behavior = chain_df["behavior_type"]

    seen_pv = (
        behavior.eq(1)
        .groupby(
            group_keys,
            sort=False,
        )
        .cummax()
    )

    valid_pv_cart = behavior.eq(3) & seen_pv
    valid_pv_fav = behavior.eq(2) & seen_pv
    valid_pv_buy = behavior.eq(4) & seen_pv

    seen_valid_cart = (
        valid_pv_cart
        .groupby(
            group_keys,
            sort=False,
        )
        .cummax()
    )

    valid_pv_cart_buy = (
        behavior.eq(4)
        & seen_valid_cart
    )

    chain_df["sequence_has_pv_cart"] = (
        valid_pv_cart.astype("uint8")
    )

    chain_df["sequence_has_pv_fav"] = (
        valid_pv_fav.astype("uint8")
    )

    chain_df["sequence_has_pv_buy"] = (
        valid_pv_buy.astype("uint8")
    )

    chain_df["sequence_has_pv_cart_buy"] = (
        valid_pv_cart_buy.astype("uint8")
    )

    chain_cols = [
        "sequence_has_pv_cart",
        "sequence_has_pv_fav",
        "sequence_has_pv_buy",
        "sequence_has_pv_cart_buy",
    ]

    user_chain = (
        chain_df
        .groupby(
            "user_id",
            sort=False,
        )[chain_cols]
        .max()
        .astype("uint8")
    )

    result = pd.concat(
        [
            recent,
            gaps,
            user_chain,
        ],
        axis=1,
    ).reset_index()

    result["user_id"] = (
        result["user_id"]
        .astype("int64")
    )

    result[
        "sequence_avg_behavior_gap_hours"
    ] = (
        result[
            "sequence_avg_behavior_gap_hours"
        ]
        .astype("float64")
    )

    for col in chain_cols:
        result[col] = (
            result[col]
            .fillna(0)
            .astype("uint8")
        )

    result = (
        result
        .sort_values("user_id")
        .reset_index(drop=True)
    )

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
            (
                "sequence_has_pv_cart",
                pa.uint8(),
            ),
            (
                "sequence_has_pv_fav",
                pa.uint8(),
            ),
            (
                "sequence_has_pv_buy",
                pa.uint8(),
            ),
            (
                "sequence_has_pv_cart_buy",
                pa.uint8(),
            ),
        ]
    )

    table = pa.Table.from_pandas(
        result,
        schema=schema,
        preserve_index=False,
    )

    date_string = label_date.strftime(
        "%Y-%m-%d"
    )

    output = (
        Path("data/splits")
        / split_name
        / "snapshots"
        / date_string
        / "features"
        / "user_sequence_features.parquet"
    )

    output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    pq.write_table(
        table,
        output,
        compression="snappy",
    )

    print("users :", f"{len(result):,}")
    print("saved :", output)


def main():

    for split_name, (
        observation_start,
        observation_end,
        label_date,
    ) in SPLIT_WINDOWS.items():
        build_one(
            split_name,
            observation_start,
            observation_end,
            label_date,
        )


if __name__ == "__main__":
    main()
