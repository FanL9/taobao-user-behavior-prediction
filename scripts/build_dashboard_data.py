"""Build dashboard datasets for stage two EDA."""

from pathlib import Path

import pyarrow.parquet as pq


ROOT = Path(__file__).resolve().parents[1]

FEATURE_DIR = ROOT / "data" / "features"
OUT_DIR = FEATURE_DIR / "dashboard"


def main():

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # 商品转化分析
    item = pq.read_table(
        FEATURE_DIR / "item_features.parquet"
    )

    item.select(
        [
            "item_id",
            "item_total_count",
            "item_pv_count",
            "item_buy_count",
            "item_buy_to_pv_rate",
        ]
    ).to_pandas().to_parquet(
        OUT_DIR / "item_conversion_analysis.parquet",
        index=False
    )


    # 类目转化分析
    category = pq.read_table(
        FEATURE_DIR / "category_features.parquet"
    )

    category.select(
        [
            "category_id",
            "category_total_count",
            "category_pv_count",
            "category_buy_count",
            "category_buy_to_pv_rate",
        ]
    ).to_pandas().to_parquet(
        OUT_DIR / "category_conversion_analysis.parquet",
        index=False
    )


    # 用户行为深度
    user = pq.read_table(
        FEATURE_DIR / "user_features.parquet"
    )

    user.select(
        [
            "user_id",
            "user_total_count",
            "user_pv_count",
            "user_cart_count",
            "user_buy_count",
            "user_buy_to_pv_rate",
            "user_is_buyer",
        ]
    ).to_pandas().to_parquet(
        OUT_DIR / "user_behavior_depth.parquet",
        index=False
    )


    # 转化漏斗
    conversion = pq.read_table(
        FEATURE_DIR / "conversion_features.parquet"
    )

    conversion.to_pandas().to_parquet(
        OUT_DIR / "conversion_funnel.parquet",
        index=False
    )


    print("dashboard datasets created")


if __name__ == "__main__":
    main()
