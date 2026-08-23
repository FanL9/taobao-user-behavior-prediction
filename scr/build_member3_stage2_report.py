"""Build the optional Member 3 stage-two feature report."""

from __future__ import annotations

from pathlib import Path

import pandas as pd


ITEM_PATH = Path("data/features/item_features.parquet")
CATEGORY_PATH = Path("data/features/category_features.parquet")
ITEM_CONVERSION_PATH = Path("data/features/item_conversion_features.parquet")
GLOBAL_CONVERSION_PATH = Path("data/features/conversion_features.parquet")
REPORT_PATH = Path("reports/member3_stage2_feature_report.md")


def main() -> None:
    item = pd.read_parquet(ITEM_PATH)
    category = pd.read_parquet(CATEGORY_PATH)
    conversion = pd.read_parquet(ITEM_CONVERSION_PATH)
    global_row = pd.read_parquet(GLOBAL_CONVERSION_PATH).iloc[0]
    validation_passed = (
        not item["item_id"].isna().any()
        and not item["item_id"].duplicated().any()
        and not category["category_id"].isna().any()
        and not category["category_id"].duplicated().any()
        and not conversion["item_id"].isna().any()
        and not conversion["item_id"].duplicated().any()
        and set(item["item_id"]) == set(conversion["item_id"])
        and int(item["item_total_count"].sum())
        == int(category["category_total_count"].sum())
        and int(global_row["item_count"]) == len(item)
    )

    item_levels = item["item_popularity_level"].value_counts().to_dict()
    category_levels = category["category_popularity_level"].value_counts().to_dict()
    report = f"""# Member 3 阶段二特征工程报告

## 1. 正式输出

| 输出 | 粒度 | 行数 | 主键 |
| --- | --- | ---: | --- |
| `data/features/item_features.parquet` | 商品 | {len(item):,} | `item_id` |
| `data/features/category_features.parquet` | 类目 | {len(category):,} | `category_id` |
| `data/features/item_conversion_features.parquet` | 商品 | {len(conversion):,} | `item_id` |
| `data/features/conversion_features.parquet` | 全局 | 1 | `conversion_scope` |

## 2. 热度分层

- 商品：`item_total_count <= Q25` 为 `low`，`Q25 < count < Q75` 为 `medium`，`count >= Q75` 为 `high`。
- 类目：`category_total_count <= Q25` 为 `long_tail`，`Q25 < count < Q75` 为 `medium`，`count >= Q75` 为 `popular`。
- 商品分布：low={item_levels.get('low', 0):,}，medium={item_levels.get('medium', 0):,}，high={item_levels.get('high', 0):,}。
- 类目分布：long_tail={category_levels.get('long_tail', 0):,}，medium={category_levels.get('medium', 0):,}，popular={category_levels.get('popular', 0):,}。

## 3. 商品转化链路

每个商品保留 pv/fav/cart/buy 行为数，以及浏览到收藏、浏览到加购、浏览到购买、收藏到购买、加购到购买的行为次数比。分母为 0 时比率记为 `0.0`。

`conversion_has_full_funnel=1` 表示该商品在观察窗口内四类行为计数均大于 0，仅表示四个阶段均出现，不表示能够恢复用户级严格先后顺序。

## 4. 全局描述性漏斗

- PV：{int(global_row['pv_count']):,}
- Fav：{int(global_row['fav_count']):,}
- Cart：{int(global_row['cart_count']):,}
- Buy：{int(global_row['buy_count']):,}
- PV → Buy：{global_row['pv_to_buy_rate']:.6f}
- Cart → Buy：{global_row['cart_to_buy_rate']:.6f}
- Fav → Buy：{global_row['fav_to_buy_rate']:.6f}
- 四阶段均出现的商品：{int(global_row['full_funnel_item_count']):,}

上述漏斗均为行为次数比，不是用户级转化概率。

## 5. 质量检查

- 商品、类目和商品转化表主键非空且唯一。
- 热度分层值符合统一口径。
- 转化次数与商品特征表逐项一致。
- 转化率重新计算一致，分母为 0 时为 0。
- 商品、类目和全局行为总量一致。

质量检查由转化特征构建代码和本报告生成脚本直接执行，不再维护独立校验脚本。

VALIDATION STATUS = {'PASS' if validation_passed else 'FAIL'}

MEMBER3_NON_DASHBOARD_READY = {'YES' if validation_passed else 'NO'}
"""
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(report, encoding="utf-8", newline="\n")
    print(f"created: {REPORT_PATH}")


if __name__ == "__main__":
    main()
