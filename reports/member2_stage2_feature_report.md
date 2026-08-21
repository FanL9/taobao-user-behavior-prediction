# Member 2 阶段二特征工程报告

## 1. 工作范围

本阶段完成 Member 2 负责的用户行为特征、用户活跃度特征、时间特征和用户行为序列特征，并对最终特征表进行质量检查。

阶段二不训练模型，也不生成未来购买标签。

## 2. 用户特征

- 输出文件：`data/features/user_features.parquet`
- 表规模：10,000 行 x 20 列
- 主键：`user_id`
- 每用户一行

本次补充字段：

- `user_avg_daily_behavior_count`
- `user_activity_level`
- `user_behavior_span_hours`

口径：

- 日均行为数 = `user_total_count / user_active_day_count`
- 活跃分层：用户总行为数大于等于全体用户中位数时为 `high`，否则为 `low`
- 行为时间跨度 = 用户最近行为时间与首次行为时间之差，单位为小时

活跃分层分布：

- high: 5,001
- low: 4,999

## 3. 时间特征

- 输出文件：`data/features/time_features.parquet`
- 表规模：744 行 x 13 列
- 粒度：`behavior_date + behavior_hour`

本次补充字段：

- `is_weekend`
- `time_period`

`is_weekend` 使用 `weekday >= 5` 判定周末。

`time_period` 分为：

- night: 00:00-05:59
- morning: 06:00-11:59
- afternoon: 12:00-17:59
- evening: 18:00-23:59

时间特征统计：

- 工作日小时记录：552
- 周末小时记录：192
- night: 186
- morning: 186
- afternoon: 186
- evening: 186

## 4. 用户行为序列特征

- 输出文件：`data/features/user_sequence_features.parquet`
- 表规模：10,000 行 x 7 列
- 主键：`user_id`
- 每用户一行

字段：

- `sequence_recent_10_behavior_types`
- `sequence_avg_behavior_gap_hours`
- `sequence_has_pv_cart`
- `sequence_has_pv_fav`
- `sequence_has_pv_buy`
- `sequence_has_pv_cart_buy`

由于原始时间只精确到小时，同一小时内的真实行为顺序无法恢复。为保证可复现性，按 `time, item_id, behavior_type` 进行确定性排序，因此该序列应视为近似序列。

最近行为序列统一保留最近 10 个 `behavior_type`。

链路特征在同一用户、同一商品内判定：

- PV -> Cart: 8,590 用户
- PV -> Fav: 6,686 用户
- PV -> Buy: 8,808 用户
- PV -> Cart -> Buy: 6,981 用户

## 5. 质量检查

质量检查包括：

- 主键缺失与重复检查
- 必需字段存在性检查
- 数值非负性检查
- 活跃分层合法值检查
- 周末标记和时段合法值检查
- 序列长度不超过 10
- 行为类型只允许 1/2/3/4
- 链路标记只允许 0/1
- `user_features` 与 `user_sequence_features` 用户数和用户集合一致

验证文件：

`outputs/member2_stage2_feature_validation.txt`

VALIDATION STATUS = PASS

## 6. 最终交付

Member 2 阶段二已完成用户行为特征、活跃度特征、时间特征、行为序列特征以及质量验证。

最终交付物：

- `data/features/user_features.parquet`
- `data/features/time_features.parquet`
- `data/features/user_sequence_features.parquet`
- `src/features/member2_user_sequence_features.py`
- `scripts/validate_member2_stage2_features.py`
- `reports/member2_stage2_feature_report.md`
- `outputs/member2_stage2_feature_validation.txt`

VALIDATION STATUS = PASS

MEMBER2_STAGE2_READY = YES

FINAL STATUS = PASS
