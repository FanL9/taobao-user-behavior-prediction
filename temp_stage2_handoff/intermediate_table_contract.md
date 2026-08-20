# Stage 2 Intermediate Table Contract

> 本文件是阶段二并行开发用的临时接口约定。当前只定义口径、键和输出路径，不要运行全量计算。

## 修改记录

| 时间 | 修改人 | 版本号 | 备注 |
| --- | --- | --- | --- |
| 2026-08-20 | Member 1 | v0.1 | 定义阶段二中间表和宽表连接合同 |

## 1. 开发前提

- 唯一业务输入 → `data/processed/user_behavior_clean.parquet`
- 小样开发时的备用输入 → `data/processed/user_behavior_clean.csv`
- 统一口径和基础字段定义 → `src/features/stage2_feature_specification.py`
- 不读取 `data/raw/`，不依赖当前固定行数，不在阶段二再次去重。
- 前置清洗逻辑可以调整，但 clean 文件路径和下列字段名作为稳定接口。

### Clean 输入字段

| 字段 | 类型口径 | 含义 |
| --- | --- | --- |
| `time` | `datetime64[ns]` | 行为时间，当前精度为小时 |
| `user_id` | `int64` | 用户标识 |
| `item_id` | `int64` | 商品标识 |
| `category_id` | `int64` | 类目标识 |
| `behavior_type` | `uint8` | `1=pv, 2=fav, 3=cart, 4=buy` |
| `behavior_name` | `string` | `pv/fav/cart/buy` |
| `behavior_date` | `date/string` | 行为日期 |
| `behavior_hour` | `uint8` | 0–23 时 |
| `weekday` | `uint8` | 周一=0，周日=6 |

## 2. 统一计算口径

| 项目 | 统一约定 |
| --- | --- |
| 观察窗口 | `2025-11-18 00:00:00` 至 `2025-12-18 23:00:00`，闭区间 |
| 时间精度 | 小时；不将同一小时内的多次行为自动视为无效行为 |
| 计数口径 | 以 clean 表中的行为记录行数计数 |
| 转化率 | 默认为行为次数比，例如 `buy_count / pv_count` |
| 分母为 0 | 转化率记为 `0.0` |
| 精度 | 计算过程保留全精度，只在展示层四舍五入 |
| 缺失补全 | 连接后计数和比率填 `0`，布尔标记填 `0`，分层字段填 `unknown` |
| 大表格式 | Parquet；本地生成，不提交 Git |
| 建模范围 | 本阶段不训练模型，不生成未来 7 天购买标签 |

> 比率是行为次数比，不是去重用户概率，因此个别比率可能大于 1。

## 3. 文件和主键总表

| 负责人 | 中间表 | 输出路径 | 粒度 | 主键 |
| --- | --- | --- | --- | --- |
| Member 2 | 用户特征表 | `data/features/user_features.parquet` | 每用户一行 | `user_id` |
| Member 2 | 时间特征表 | `data/features/time_features.parquet` | 每日每小时一行 | `behavior_date + behavior_hour` |
| Member 2 | 用户序列特征表 | `data/features/user_sequence_features.parquet` | 每用户一行 | `user_id` |
| Member 3 | 商品特征表 | `data/features/item_features.parquet` | 每商品一行 | `item_id` |
| Member 3 | 类目特征表 | `data/features/category_features.parquet` | 每类目一行 | `category_id` |
| Member 3 | 转化链路特征表 | `data/features/item_conversion_features.parquet` | 每商品一行 | `item_id` |
| Member 1 | 用户-商品交互表 | `data/features/user_item_features.parquet` | 每用户-商品一行 | `user_id + item_id` |
| Member 1 | 初版特征宽表 | `data/features/user_item_feature_table.parquet` | 每用户-商品一行 | `user_id + item_id` |

## 4. Member 2 输出合同

### 4.1 `user_features.parquet`

必须唯一键：`user_id`。字段统一使用 `user_` 前缀，不要输出商品或类目粒度的行。

| 必需字段 | 类型 | 计算口径 |
| --- | --- | --- |
| `user_id` | `int64` | 主键 |
| `user_total_count` | `int64` | 用户全部行为数 |
| `user_pv_count` | `int64` | `behavior_name='pv'` 的行数 |
| `user_fav_count` | `int64` | `behavior_name='fav'` 的行数 |
| `user_cart_count` | `int64` | `behavior_name='cart'` 的行数 |
| `user_buy_count` | `int64` | `behavior_name='buy'` 的行数 |
| `user_buy_to_pv_rate` | `float64` | `user_buy_count / user_pv_count` |
| `user_active_day_count` | `int32` | 去重 `behavior_date` 数 |
| `user_avg_daily_behavior_count` | `float64` | `user_total_count / user_active_day_count` |
| `user_first_behavior_time` | `datetime64[ns]` | `min(time)` |
| `user_last_behavior_time` | `datetime64[ns]` | `max(time)` |
| `user_behavior_span_hours` | `float64` | `max(time)-min(time)` 的小时数 |
| `user_activity_level` | `string/category` | `user_total_count >= 全体用户中位数` 为 `high`，否则为 `low` |

### 4.2 `time_features.parquet`

必须唯一键：`behavior_date + behavior_hour`。`behavior_date` 统一转为 `date32`。

| 必需字段 | 类型 | 计算口径 |
| --- | --- | --- |
| `behavior_date` | `date32` | 日期主键 |
| `behavior_hour` | `uint8` | 小时主键 |
| `weekday` | `uint8` | 周一=0，周日=6 |
| `time_is_weekend` | `uint8` | `weekday in (5, 6)` |
| `time_period` | `string/category` | `00-05=night, 06-11=morning, 12-17=afternoon, 18-23=evening` |
| `time_total_count` | `int64` | 该日该小时全部行为数 |
| `time_pv_count` | `int64` | 该日该小时浏览数 |
| `time_fav_count` | `int64` | 该日该小时收藏数 |
| `time_cart_count` | `int64` | 该日该小时加购数 |
| `time_buy_count` | `int64` | 该日该小时购买数 |
| `time_unique_user_count` | `int64` | 该日该小时去重用户数 |
| `time_unique_item_count` | `int64` | 该日该小时去重商品数 |
| `time_buy_to_pv_rate` | `float64` | `time_buy_count / time_pv_count` |

### 4.3 `user_sequence_features.parquet`

必须唯一键：`user_id`。因时间只到小时，同小时内的真实先后顺序不可恢复；代码中统一用 `time, item_id, behavior_type` 升序作为确定性排序，并在质量报告标注这是近似序列。

| 必需字段 | 类型 | 计算口径 |
| --- | --- | --- |
| `user_id` | `int64` | 主键 |
| `sequence_last_10_behavior_types` | `list<uint8>` | 确定性排序后最近 10 个行为类型 |
| `sequence_mean_gap_hours` | `float64` | 相邻记录时间差的平均小时数 |
| `sequence_pv_to_cart_item_count` | `int64` | 用户中同商品满足 `pv_time <= cart_time` 的去重商品数 |
| `sequence_pv_to_buy_item_count` | `int64` | 用户中同商品满足 `pv_time <= buy_time` 的去重商品数 |
| `sequence_has_full_chain` | `uint8` | 是否存在同商品 `pv_time <= cart_time <= buy_time` |

## 5. Member 3 输出合同

### 5.1 `item_features.parquet`

必须唯一键：`item_id`。`category_id` 是后续连接类目表的外键；若同一商品出现多个类目，取出现次数最多的类目，并以最小 `category_id` 破除平局。

| 必需字段 | 类型 | 计算口径 |
| --- | --- | --- |
| `item_id` | `int64` | 主键 |
| `category_id` | `int64` | 类目外键 |
| `item_total_count` | `int64` | 商品全部行为数 |
| `item_pv_count` | `int64` | 商品浏览数 |
| `item_fav_count` | `int64` | 商品收藏数 |
| `item_cart_count` | `int64` | 商品加购数 |
| `item_buy_count` | `int64` | 商品购买数 |
| `item_unique_user_count` | `int64` | 商品去重交互用户数 |
| `item_unique_buyer_count` | `int64` | 商品去重购买用户数 |
| `item_buy_to_pv_rate` | `float64` | `item_buy_count / item_pv_count` |
| `item_popularity_level` | `string/category` | `< Q25` 为 `low`，`Q25–Q75` 为 `medium`，`>= Q75` 为 `high` |

### 5.2 `category_features.parquet`

必须唯一键：`category_id`。

| 必需字段 | 类型 | 计算口径 |
| --- | --- | --- |
| `category_id` | `int64` | 主键 |
| `category_total_count` | `int64` | 类目全部行为数 |
| `category_pv_count` | `int64` | 类目浏览数 |
| `category_fav_count` | `int64` | 类目收藏数 |
| `category_cart_count` | `int64` | 类目加购数 |
| `category_buy_count` | `int64` | 类目购买数 |
| `category_unique_user_count` | `int64` | 类目去重交互用户数 |
| `category_unique_item_count` | `int64` | 类目去重商品数 |
| `category_buy_to_pv_rate` | `float64` | `category_buy_count / category_pv_count` |
| `category_popularity_level` | `string/category` | `< Q25` 为 `long_tail`，`Q25–Q75` 为 `medium`，`>= Q75` 为 `popular` |

### 5.3 `item_conversion_features.parquet`

必须唯一键：`item_id`。转化表按商品粒度输出，使用 `item_id` 可直接连入用户-商品宽表。

| 必需字段 | 类型 | 计算口径 |
| --- | --- | --- |
| `item_id` | `int64` | 主键 |
| `conversion_pv_to_buy_rate` | `float64` | `buy_count / pv_count` |
| `conversion_pv_to_cart_rate` | `float64` | `cart_count / pv_count` |
| `conversion_cart_to_buy_rate` | `float64` | `buy_count / cart_count` |
| `conversion_fav_to_buy_rate` | `float64` | `buy_count / fav_count` |
| `conversion_has_full_funnel` | `uint8` | pv、cart、buy 均大于 0 则为 1 |

## 6. Member 1 后续基表合同

### 6.1 `user_item_features.parquet`

这是特征宽表的唯一基表，必须保证 `user_id + item_id` 唯一。

| 必需字段 | 类型 | 用途 |
| --- | --- | --- |
| `user_id` | `int64` | 连接用户表和序列表 |
| `item_id` | `int64` | 连接商品表和转化表 |
| `category_id` | `int64` | 连接类目表 |
| `ui_pv_count` | `int64` | 用户对商品的浏览数 |
| `ui_fav_count` | `int64` | 用户对商品的收藏数 |
| `ui_cart_count` | `int64` | 用户对商品的加购数 |
| `ui_buy_count` | `int64` | 用户对商品的购买数 |
| `ui_last_interaction_time` | `datetime64[ns]` | 最近交互时间 |
| `last_interaction_date` | `date32` | 连接时间表 |
| `last_interaction_hour` | `uint8` | 连接时间表 |
| `ui_has_buy` | `uint8` | 是否发生过购买 |

## 7. 宽表连接顺序

目标输出：`data/features/user_item_feature_table.parquet`，主键仍为 `user_id + item_id`。

| 顺序 | 左表 | 右表 | 连接键 | 基数关系 |
| ---: | --- | --- | --- | --- |
| 1 | `user_item_features` | `user_features` | `user_id` | 多对一 |
| 2 | 上一步结果 | `user_sequence_features` | `user_id` | 多对一 |
| 3 | 上一步结果 | `item_features` | `item_id` | 多对一 |
| 4 | 上一步结果 | `item_conversion_features` | `item_id` | 多对一 |
| 5 | 上一步结果 | `category_features` | `category_id` | 多对一 |
| 6 | 上一步结果 | `time_features` | `last_interaction_date + last_interaction_hour` 对应 `behavior_date + behavior_hour` | 多对一 |

全部使用左连接。每次连接后都必须检查：

1. 行数与 `user_item_features` 相同。
2. `user_id + item_id` 仍唯一。
3. 右表的连接键在连接前已唯一。
4. 不使用无键的 `merge` 或多对多连接。

## 8. 建议代码文件

| 负责人 | 代码路径 | 建议入口函数 |
| --- | --- | --- |
| Member 2 | `src/features/user_features.py` | `build_user_features(input_path, output_path, window)` |
| Member 2 | `src/features/time_features.py` | `build_time_features(input_path, output_path, window)` |
| Member 2 | `src/features/user_sequence_features.py` | `build_user_sequence_features(input_path, output_path, window)` |
| Member 2 | `scripts/build_member2_features.py` | 统一调用上述三个函数 |
| Member 3 | `src/features/item_features.py` | `build_item_features(input_path, output_path, window)` |
| Member 3 | `src/features/category_features.py` | `build_category_features(input_path, output_path, window)` |
| Member 3 | `src/features/item_conversion_features.py` | `build_item_conversion_features(input_path, output_path, window)` |
| Member 3 | `scripts/build_member3_features.py` | 统一调用上述三个函数 |

代码可以现在按这些函数和键编写，但暂时不运行，也不生成上述 Parquet 结果。

## 9. 合并前检查清单

- [ ] 输入只使用 clean Parquet/CSV 稳定字段。
- [ ] 输出路径、表名、主键和字段前缀与本文一致。
- [ ] 每张表主键无缺失、无重复。
- [ ] 计数字段非负，分母为 0 时比率为 `0.0`。
- [ ] 同小时序列的局限已在代码注释和质量说明中保留。
- [ ] 未训练模型，未生成未来标签。
