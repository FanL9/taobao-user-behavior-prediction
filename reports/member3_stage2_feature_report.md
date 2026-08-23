# Member 3 阶段二特征工程报告

## 1. 正式输出

| 输出 | 粒度 | 行数 | 主键 |
| --- | --- | ---: | --- |
| `data/features/item_features.parquet` | 商品 | 2,876,947 | `item_id` |
| `data/features/category_features.parquet` | 类目 | 8,916 | `category_id` |
| `data/features/item_conversion_features.parquet` | 商品 | 2,876,947 | `item_id` |
| `data/features/conversion_features.parquet` | 全局 | 1 | `conversion_scope` |

## 2. 热度分层

- 商品：`item_total_count <= Q25` 为 `low`，`Q25 < count < Q75` 为 `medium`，`count >= Q75` 为 `high`。
- 类目：`category_total_count <= Q25` 为 `long_tail`，`Q25 < count < Q75` 为 `medium`，`count >= Q75` 为 `popular`。
- 商品分布：low=723,595，medium=1,321,364，high=831,988。
- 类目分布：long_tail=2,280，medium=4,407，popular=2,229。

## 3. 商品转化链路

每个商品保留 pv/fav/cart/buy 行为数，以及浏览到收藏、浏览到加购、浏览到购买、收藏到购买、加购到购买的行为次数比。分母为 0 时比率记为 `0.0`。

`conversion_has_full_funnel=1` 表示该商品在观察窗口内四类行为计数均大于 0，仅表示四个阶段均出现，不表示能够恢复用户级严格先后顺序。

## 4. 全局描述性漏斗

- PV：11,550,581
- Fav：242,556
- Cart：343,564
- Buy：120,205
- PV → Buy：0.010407
- Cart → Buy：0.349877
- Fav → Buy：0.495576
- 四阶段均出现的商品：13,892

上述漏斗均为行为次数比，不是用户级转化概率。

## 5. 质量检查

- 商品、类目和商品转化表主键非空且唯一。
- 热度分层值符合统一口径。
- 转化次数与商品特征表逐项一致。
- 转化率重新计算一致，分母为 0 时为 0。
- 商品、类目和全局行为总量一致。

质量检查由转化特征构建代码和本报告生成脚本直接执行，不再维护独立校验脚本。

VALIDATION STATUS = PASS

MEMBER3_NON_DASHBOARD_READY = YES
