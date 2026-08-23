# 阶段二初版特征宽表报告

## 1. 输出

- 文件：`data/features/user_item_feature_table.parquet`
- 粒度：每个 `user_id + item_id` 一行
- 行数：4,686,904
- 字段数：82
- 本地文件大小：225.28 MB
- Git：仅本地生成，不上传

## 2. 特征来源

| 特征组 | 输入 |
| --- | --- |
| 用户行为与活跃度 | `user_features.parquet` |
| 用户序列与行为链路 | `user_sequence_features.parquet` |
| 商品行为与热度 | `item_features.parquet` |
| 类目行为与热度 | `category_features.parquet` |
| 最近交互时间特征 | `time_features.parquet` |
| 用户—商品交互 | `user_item_features.parquet` |
| 商品转化链路 | `item_conversion_features.parquet` |

最近10次行为在原序列表中是列表类型；为支持大表连接，在宽表中确定性编码为 `1|2|3|4` 形式的字符串，行为映射仍为 `1=pv, 2=fav, 3=cart, 4=buy`。

## 3. 连接方式

- 以 `user_item_features` 为唯一基表。
- 用户和序列表按 `user_id` 左连接。
- 商品和商品转化表按 `item_id` 左连接。
- 类目表按商品表提供的 `category_id` 左连接。
- 时间表按最近交互日期和小时左连接。
- 每张右表连接键在连接前均检查唯一；每次连接后行数必须保持不变。

## 4. 质量检查

| 检查 | 结果 |
| --- | --- |
| 主键重复 | 0 |
| 全表缺失值 | 0 |
| 负数计数特征 | 0 |
| 非有限或负数比率 | 0 |
| Member 2/3 重复计数字段一致性 | PASS |
| 最终状态 | PASS |

附加检查包括所有0/1字段合法、分类字段合法、用户—商品购买标记与购买次数一致、最近交互日期/小时与时间戳一致，以及商品转化次数与商品基础次数逐项一致。

验证结果：`outputs/stage2_feature_table_validation.json`（本地生成，不上传 Git）。

STAGE2_INITIAL_FEATURE_TABLE_READY = YES
