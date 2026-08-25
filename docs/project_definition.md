# 项目全流程统一口径

本文件是淘宝用户行为预测项目的最高级口径与标准文件，用于统一数据接入、数据清洗、数据质量、EDA、特征工程、样本与标签、模型训练、模型评估、看板、报告和结果交付中的定义。

> 所有成员新增或修改项目口径时，必须同步更新本文件和修改记录。

## 修改记录

| 时间 | 修改人 | 版本号 | 备注 |
| --- | --- | --- | --- |
| 2026-08-17 | Member 1 | v1.0 | 初始化项目全流程统一口径文件 |
| 2026-08-20 | Member 1 | v1.1 | 补全阶段一和阶段二已确定的数据、清洗、统计、特征和中间表口径 |
| 2026-08-20 | Member 1 | v1.2 | 记录阶段二四张已生成中间表，并允许 `data/features/` 上传 Git |
| 2026-08-20 | Member 1 | v1.3 | 取消独立特征规格代码和字典文件，特征口径统一收口到本文件 |
| 2026-08-25 | Member 1 | v1.4 | 明确阶段三样本粒度、未来 1 天购买目标、观察窗口、正负样本和固定时间切分口径 |
| 2026-08-25 | Member 1 | v1.5 | 按阶段三固定窗口完成 Member 2 建模样本与标签生成，并通过时间泄露审计 |

## 1. 文档权威性与冲突处理

1. `docs/project_definition.md` 是项目口径的唯一权威来源。
2. 代码、SQL、中间表、看板和报告必须与本文件一致。
3. 如实现与本文件冲突，先停止使用冲突结果，由 Member 1 确认后同步修改代码和本文件。
4. 报告中的数值必须来自当前口径下重新生成的结果，不得复用已废弃口径的历史数值。
5. 历史“删除全部四元组重复”口径已废弃；由此产生的 6,213,379 行 clean 数据、旧版 EDA 数值和 `outputs/user_behavior_cleaning_report.json` 不得作为当前正式结论。
6. 当前清洗规则实现以 `src/data/user_behavior_cleaning_pipeline.py` 为准，当前正式质量报告为 `reports/member2_data_quality_report.md`。

## 2. 项目范围与阶段边界

| 项目 | 统一口径 |
| --- | --- |
| 项目目标 | 基于用户行为数据完成数据治理、EDA、特征工程，并为后续购买预测建模做准备 |
| 阶段一 | 数据接入、基础治理、标准 clean 数据和基础 EDA |
| 阶段二 | 用户、商品、类目、时间、序列和转化特征，以及 EDA 看板初版 |
| 阶段二限制 | 不训练模型，不生成阶段三购买标签 |
| 阶段三 | 按三段固定特征基准日范围构建训练、验证和测试样本，分别使用 `2025-12-08`、`2025-12-15`、`2025-12-18` 作为单日标签窗口，详细口径见第 15 节 |

## 3. 数据来源、路径与存储口径

| 项目 | 统一口径 |
| --- | --- |
| 原始数据外部来源 | 尚未补充，在有可验证来源前不写推测性来源 |
| 阶段一输入文件 | `data/raw/user_behavior_processed.csv` |
| 原始 Parquet 副本 | `data/raw/user_behavior_processed.parquet` |
| SQLite 数据库 | `database/taobao_user_behavior.db` |
| SQLite 原始表 | `user_behavior_processed` |
| SQLite 行为映射视图 | `vw_user_behavior_mapped` |
| 标准 clean CSV | `data/processed/user_behavior_clean.csv` |
| 标准 clean Parquet | `data/processed/user_behavior_clean.parquet` |
| Python 阶段二输入 | clean Parquet 优先，clean CSV 仅作小样或兼容备用 |
| SQL 用途 | SQLite 用于 SQL 验证和 DBeaver 查看，不作为阶段二特征的权威输入 |
| 原始文件保护 | 原始 CSV 不直接修改；所有派生结果写入 `data/processed/`、`data/interim/` 或 `data/features/` |
| Git 管理 | `data/raw/`、`data/processed/` 和数据库大文件不上传；`data/features/` 中的 CSV、JSON 和 Parquet 允许上传；代码、SQL、文档和报告可上传 |
| 本地初始化 | 统一运行 `python scripts/setup_local_database.py` |

## 4. 当前输入数据快照

> 本节是当前数据快照，不是对未来数据规模的硬编码假设。代码不得依赖固定行数。

| 检查项 | 当前结果 |
| --- | ---: |
| 输入记录数 | 12,256,906 |
| 唯一用户数 | 10,000 |
| 唯一商品数 | 2,876,947 |
| 唯一类目数 | 8,916 |
| 行为类型数 | 4 |
| 实际时间范围 | `2025-11-18 00:00:00` 至 `2025-12-18 23:00:00` |
| 五个原始核心字段缺失 | 0 |
| 当前正式 clean 行数 | 12,256,906 |

当前实际用户数为 10,000，与外部资料中“约 100 万独立用户”的描述不一致。所有报告以当前实际数据检查结果为准。

## 5. 原始输入字段口径

| 字段 | 输入格式 | 含义 | 合法性 |
| --- | --- | --- | --- |
| `time` | `YYYY-MM-DD HH` | 行为时间，仅精确到小时 | 必须严格匹配格式并可解析 |
| `user_id` | 整数 | 用户标识 | 非空正整数，且可安全表示为 Int64/SQLite INTEGER |
| `item_id` | 整数 | 商品标识 | 非空正整数，且可安全表示为 Int64/SQLite INTEGER |
| `item_category` | 整数 | 原始类目标识 | 非空正整数，清洗后改名为 `category_id` |
| `behavior_type` | `1/2/3/4` | 行为数字编码 | 仅允许 1、2、3、4 |

ID 是标识符，不对 `user_id`、`item_id`、`item_category/category_id` 使用 IQR、3σ 或数值大小判定业务异常。

## 6. 行为与时间口径

### 6.1 行为映射

| `behavior_type` | `behavior_name` | 中文含义 |
| ---: | --- | --- |
| 1 | `pv` | 浏览 |
| 2 | `fav` | 收藏 |
| 3 | `cart` | 加购 |
| 4 | `buy` | 购买 |

### 6.2 时间规则

| 项目 | 统一口径 |
| --- | --- |
| 时区 | 源数据未提供时区，统一按无时区的源时间处理，不自行转换 |
| 输入精度 | 小时；不声称拥有分钟或秒级先后顺序 |
| clean `time` | `datetime64[ns]`；CSV 显示格式为 `YYYY-MM-DD HH:MM:SS` |
| `behavior_date` | 从 `time` 派生的 `YYYY-MM-DD` |
| `behavior_hour` | 0–23 的 `uint8` |
| `weekday` | 周一=0，周日=6 |
| 工作日 | `weekday` 为 0–4 |
| 周末 | `weekday` 为 5或6 |
| 时段 | `00–05=night`，`06–11=morning`，`12–17=afternoon`，`18–23=evening` |
| 业务时间边界 | 只有显式配置 `allowed_start/allowed_end` 时才过滤；边界为包含关系 |

## 7. 标准 clean 数据口径

### 7.1 Clean 字段和类型

| 字段 | 类型口径 | 来源/规则 |
| --- | --- | --- |
| `time` | `datetime64[ns]` | 严格解析原始 `time` |
| `user_id` | `int64` | 原始用户 ID |
| `item_id` | `int64` | 原始商品 ID |
| `category_id` | `int64` | 原 `item_category` 标准化改名 |
| `behavior_type` | `uint8` | 1–4 |
| `behavior_name` | `string` | 按统一行为映射生成 |
| `behavior_date` | `string/date` | 由 `time` 派生的日期 |
| `behavior_hour` | `uint8` | 由 `time` 派生的小时 |
| `weekday` | `uint8` | 由 `time` 派生，周一=0 |

### 7.2 清洗顺序

1. 检查输入列名及顺序。
2. 去除字段首尾空格。
3. 删除任一核心字段缺失的记录。
4. 删除非法 `behavior_type`、非法 ID 和无法解析的时间。
5. 如配置业务时间边界，删除边界外记录。
6. 执行异常高频重复规则。
7. 标准化字段并生成 clean CSV/Parquet。
8. 回读输出，验证列、类型、行数和高频组。

### 7.3 重复与异常高频规则

| 项目 | 统一口径 |
| --- | --- |
| 诊断四元组 | `user_id + item_id + behavior_type + time` |
| 完全重复 | 五个原始字段都相同；只作数据诊断，不自动代表脏数据 |
| 2–59 次相同四元组 | 全部保留，因小时精度无法区分真实重复行为和重复导入 |
| 60 次及以上 | 标记为异常高频/疑似恶意重复组，仅保留该组首条，阈值 60 包含边界 |
| 阈值含义 | 在一个源数据小时桶内出现次数，不得表述为“一分钟内 60 次” |
| 当前结果 | 最大四元组次数为 22，无达到 60 的组，因此当前未因重复删除记录 |

完全重复行数和四元组重复行数是“每组保留首条后的其余行数”，只是诊断指标，不得直接等同于删除量。

## 8. 数据质量口径

| 检查项 | 统一口径 |
| --- | --- |
| 数据规模 | 总行数、去重用户数、商品数、类目数、行为类型数和时间范围 |
| 缺失值 | 分字段统计缺失数，并统计任一关键字段缺失的记录数 |
| 非法行为 | `behavior_type` 不在 1–4 中 |
| 非法 ID | 空值、非正整数或超出 Int64/SQLite INTEGER 范围 |
| 非法时间 | 不匹配 `%Y-%m-%d %H` 或无法解析 |
| 超出时间范围 | 仅在显式配置允许边界时统计并删除 |
| 重复诊断 | 同时报告完全重复和四元组重复，但删除量只按异常高频规则计算 |
| 问题数量 | 各问题统计可重叠，不得直接相加得到删除量 |
| 删除对账 | 使用互斥删除原因对账，其合计必须等于原始行数减 clean 行数 |
| 全局一致性 | 分块处理时必须识别跨 chunk 的统计和高频组 |

## 9. 基础统计与 EDA 口径

| 指标 | 统一口径 |
| --- | --- |
| 数据来源 | 只基于当前正式 clean Parquet/CSV，不直接基于 `user_behavior_processed` 下最终结论 |
| 用户数 | `COUNT(DISTINCT user_id)` |
| 商品数 | `COUNT(DISTINCT item_id)` |
| 类目数 | `COUNT(DISTINCT category_id)` |
| 行为总量 | clean 表的行数 |
| 浏览/收藏/加购/购买量 | 对应 `behavior_name` 的行数 |
| 行为占比 | 对应行为行数 / 四类合法行为总行数 |
| 活跃用户 | 指定统计窗口内至少有 1 条行为记录的用户 |
| 购买用户 | 至少有 1 条 `buy` 记录的用户 |
| 未购买用户 | 窗口内有行为但完全没有 `buy` 记录的用户 |
| 复购用户 | 至少有 2 条 `buy` 行为记录的用户；当前数据无订单 ID，因此不声称是两张独立订单 |
| 热门商品 | 按 `buy_count` 降序的前 10 个商品 |
| 热门类目 | 按 `buy_count` 降序的前 10 个类目 |
| 类目购买占比 | 该类目 `buy_count` / 全部类目 `buy_count` |
| 日期行为量 | 按 `behavior_date` 分组的行数 |
| 小时行为量 | 按 `behavior_hour` 分组的行数 |

### 9.1 描述性转化漏斗

- 阶段顺序固定为 `pv → fav → cart → buy`。
- 每层数值是对应行为记录数，相对 PV 比率为 `stage_count / pv_count`。
- 该漏斗只是行为量的描述性对比，不代表用户必然按固定顺序转化，也不是去重用户转化率。

## 10. 阶段二特征工程总口径

| 项目 | 统一口径 |
| --- | --- |
| 权威输入 | `data/processed/user_behavior_clean.parquet` |
| 备用输入 | `data/processed/user_behavior_clean.csv` |
| 观察窗口 | `2025-11-18 00:00:00` 至 `2025-12-18 23:00:00`，闭区间 |
| 近期性参考时间 | `2025-12-19 00:00:00` |
| 计数 | 以 clean 表中的行为记录行数计数，阶段二不再去重 |
| 基础转化率 | `fav_count/pv_count`、`cart_count/pv_count`、`buy_count/pv_count` |
| 链路转化率 | `buy_count/pv_count`、`cart_count/pv_count`、`buy_count/cart_count`、`buy_count/fav_count` |
| 分母为 0 | 比率记为 `0.0` |
| 比率含义 | 行为次数比，不是去重用户概率，数值可能大于 1 |
| 计算精度 | 计算和存储保留全精度，只在展示层四舍五入 |
| 特征命名 | 使用 snake_case，按粒度使用 `user_`、`item_`、`category_`、`time_`、`sequence_`、`conversion_`、`ui_` 前缀 |
| 主键 | ID 字段使用 `int64`，主键不允许缺失或重复 |
| 连接后缺失 | 计数和比率填 `0`，布尔/0-1 标记填 `0`，分层字段填 `unknown` |
| 大表格式 | Parquet；`user_item_features.parquet` 和 `user_item_feature_table.parquet` 只在本地生成，其他特征表可按 Git 规则上传 |
| 口径与字段来源 | 本文件是唯一口径来源，不再另行维护特征字典代码或规格文件 |
| 基础聚合表构建实现 | `src/features/stage2_intermediate_tables.py` |
| 基础聚合表运行入口 | `scripts/build_stage2_intermediate_tables.py` |
| 用户序列表构建入口 | `scripts/build_member2_stage2_features.py` |
| Member 3 转化特征实现 | `src/features/conversion_features.py` |
| Member 3 运行入口 | `scripts/build_member3_stage2_features.py` |
| 初版宽表实现 | `src/features/stage2_feature_table.py` |
| 初版宽表运行入口 | `scripts/build_stage2_feature_table.py` |

## 11. 阶段二中间表、粒度和键

| 中间表 | 输出路径 | 粒度 | 主键/唯一键 | 当前状态 |
| --- | --- | --- | --- | --- |
| 用户特征表 | `data/features/user_features.parquet` | 每用户一行 | `user_id` | 已生成，10,000 行 |
| 时间特征表 | `data/features/time_features.parquet` | 每日每小时一行 | `behavior_date + behavior_hour` | 已生成，744 行 |
| 用户序列特征表 | `data/features/user_sequence_features.parquet` | 每用户一行 | `user_id` | 已生成，10,000 行 |
| 商品特征表 | `data/features/item_features.parquet` | 每商品一行 | `item_id` | 已生成，2,876,947 行 |
| 类目特征表 | `data/features/category_features.parquet` | 每类目一行 | `category_id` | 已生成，8,916 行 |
| 商品转化链路表 | `data/features/item_conversion_features.parquet` | 每商品一行 | `item_id` | 已生成，2,876,947 行 |
| 全局转化漏斗表 | `data/features/conversion_features.parquet` | 全局一行 | `conversion_scope` | 已生成，1 行 |
| 用户-商品交互表 | `data/features/user_item_features.parquet` | 每用户-商品一行 | `user_id + item_id` | 已生成，4,686,904 行 |
| 用户-商品特征宽表 | `data/features/user_item_feature_table.parquet` | 每用户-商品一行 | `user_id + item_id` | 已生成，4,686,904 行、82 列 |

### 11.1 阶段二分工交付状态（2026-08-23 检查）

| 成员 | 已完成并验证 | 仍需补充 |
| --- | --- | --- |
| Member 2 | 用户、时间、高峰小时和序列特征已生成；主键、必需字段、非负值、0/1 标记和用户集合校验为 `PASS` | 非看板范围无 |
| Member 3 | 商品/类目基础特征、Q25/Q75 热度分层、商品粒度转化链路、全局漏斗、质量检查和正式报告已完成，校验为 `PASS` | 非看板范围无 |
| Member 1 整合 | 用户、序列、商品、类目、时间、用户-商品和转化特征已整合为 82 列初版宽表，校验为 `PASS` | 待正式建模口径确定后再构建标签和时间切分 |

### 11.2 外键和连接规则

1. 宽表以 `user_item_features` 为唯一基表。
2. 用户特征表和序列特征表按 `user_id` 连接。
3. 商品特征表和商品转化表按 `item_id` 连接。
4. 类目特征表按 `category_id` 连接。
5. 时间特征表按 `last_interaction_date + last_interaction_hour` 对应 `behavior_date + behavior_hour` 连接。
6. 全部使用左连接，右表在连接前必须保证连接键唯一。
7. 每次连接后行数必须与基表相同，`user_id + item_id` 必须仍然唯一，禁止多对多连接。
8. 序列表的最近 10 次行为在原表中保留 `list<int64>`；宽表中为支持 Arrow 连接，编码为 `1|2|3|4` 形式的字符串。

### 11.3 商品与类目关系

商品表按 `item_id` 唯一。如同一商品对应多个 `category_id`，取该商品中出现次数最多的类目；如出现次数并列，取最小 `category_id`。

## 12. 阶段二具体特征口径

> 当前已生成的正式特征表字段以下表为准。补充 CSV 不取代正式 Parquet；新增字段或分层时必须先更新本文件。

### 12.0 当前基础表字段

| 表 | 当前字段 |
| --- | --- |
| `user_features` | `user_id`, `user_total_count`, `user_pv_count`, `user_fav_count`, `user_cart_count`, `user_buy_count`, `user_unique_item_count`, `user_unique_category_count`, `user_active_day_count`, `user_avg_daily_behavior_count`, `user_activity_level`, `user_behavior_span_hours`, `user_first_behavior_time`, `user_last_behavior_time`, `user_recency_hours`, `user_fav_to_pv_rate`, `user_cart_to_pv_rate`, `user_buy_to_pv_rate`, `user_is_buyer`, `user_is_repeat_buyer` |
| `item_features` | `item_id`, `category_id`, `item_total_count`, `item_pv_count`, `item_fav_count`, `item_cart_count`, `item_buy_count`, `item_unique_user_count`, `item_unique_buyer_count`, `item_active_day_count`, `item_popularity_level`, `item_fav_to_pv_rate`, `item_cart_to_pv_rate`, `item_buy_to_pv_rate` |
| `category_features` | `category_id`, `category_total_count`, `category_pv_count`, `category_fav_count`, `category_cart_count`, `category_buy_count`, `category_unique_user_count`, `category_unique_item_count`, `category_unique_buyer_count`, `category_popularity_level`, `category_fav_to_pv_rate`, `category_cart_to_pv_rate`, `category_buy_to_pv_rate` |
| `time_features` | `behavior_date`, `behavior_hour`, `weekday`, `is_weekend`, `time_period`, `time_is_peak_hour`, `time_total_count`, `time_pv_count`, `time_fav_count`, `time_cart_count`, `time_buy_count`, `time_unique_user_count`, `time_unique_item_count`, `time_buy_to_pv_rate` |
| `user_sequence_features` | `user_id`, `sequence_recent_10_behavior_types`, `sequence_avg_behavior_gap_hours`, `sequence_has_pv_cart`, `sequence_has_pv_fav`, `sequence_has_pv_buy`, `sequence_has_pv_cart_buy` |
| `user_item_features` | `user_id`, `item_id`, `ui_pv_count`, `ui_fav_count`, `ui_cart_count`, `ui_buy_count`, `ui_last_interaction_time`, `ui_last_interaction_date`, `ui_last_interaction_hour`, `ui_has_bought` |
| `item_conversion_features` | `item_id`, `conversion_pv_count`, `conversion_fav_count`, `conversion_cart_count`, `conversion_buy_count`, `conversion_pv_to_fav_rate`, `conversion_pv_to_cart_rate`, `conversion_pv_to_buy_rate`, `conversion_fav_to_buy_rate`, `conversion_cart_to_buy_rate`, `conversion_has_full_funnel` |
| `conversion_features` | `conversion_scope`, `item_count`, `full_funnel_item_count`, `pv_count`, `fav_count`, `cart_count`, `buy_count`, `pv_to_fav_rate`, `pv_to_cart_rate`, `pv_to_buy_rate`, `fav_to_buy_rate`, `cart_to_buy_rate` |

### 12.1 用户特征

| 特征 | 口径 |
| --- | --- |
| 总行为和四类行为数 | 按 `user_id` 分组的总行数及 pv/fav/cart/buy 行数 |
| 交互广度 | 用户去重 `item_id` 数和去重 `category_id` 数 |
| 活跃天数 | 用户去重 `behavior_date` 数 |
| 日均行为数 | `user_total_count / user_active_day_count` |
| 首次/最近行为 | 用户 `min(time)` / `max(time)` |
| 行为时间跨度 | `max(time) - min(time)` 的小时数 |
| 近期性 | 参考时间与用户最近行为时间的小时差 |
| 购买用户标记 | `buy_count >= 1` 为 1 |
| 复购用户标记 | `buy_count >= 2` 为 1 |
| 活跃分层 | `user_total_count >= 全体用户中位数` 为 `high`，否则为 `low` |

### 12.2 商品与类目特征

| 特征 | 口径 |
| --- | --- |
| 商品行为 | 按 `item_id` 分组的总行为数、四类行为数、去重用户数、去重购买用户数和活跃天数 |
| 类目行为 | 按 `category_id` 分组的总行为数、四类行为数、去重用户数、去重商品数和去重购买用户数 |
| 商品热度 | `item_total_count <= Q25` 为 `low`，`Q25 < count < Q75` 为 `medium`，`>= Q75` 为 `high` |
| 类目热度 | `category_total_count <= Q25` 为 `long_tail`，`Q25 < count < Q75` 为 `medium`，`>= Q75` 为 `popular` |

上述分层已分别写入 `item_popularity_level` 和 `category_popularity_level`。

### 12.3 时间特征

- 粒度为 `behavior_date + behavior_hour`。
- 包含工作日/周末、时段、总行为数、四类行为数、去重用户数、去重商品数和购买/浏览比率。
- 先将观察窗内行为按 24 个小时汇总，小时总行为量 `>= P80` 的小时在 `time_is_peak_hour` 中记为 1，否则为 0；当前高峰小时为 19–23 点。

### 12.4 序列特征

- 因时间仅精确到小时，同小时内的真实行为顺序不可恢复。
- 为保证代码可复现，序列按 `time, item_id, behavior_type` 升序确定性排序，但必须在报告中标注为近似序列。
- 最近序列统一取最近 10 个 `behavior_type`。
- 最近行为序列字段名为 `sequence_recent_10_behavior_types`，按上述确定性顺序保存最近最多 10 个行为类型。
- 用户行为间隔字段名为 `sequence_avg_behavior_gap_hours`，定义为相邻两次确定性排序行为时间差的平均小时数；用户只有 1 条行为时记为 `0.0`。
- `sequence_has_pv_cart`：同一用户、同一商品存在 `pv_time <= cart_time` 时记为 1，否则为 0。
- `sequence_has_pv_fav`：同一用户、同一商品存在 `pv_time <= fav_time` 时记为 1，否则为 0。
- `sequence_has_pv_buy`：同一用户、同一商品存在 `pv_time <= buy_time` 时记为 1，否则为 0。
- `sequence_has_pv_cart_buy`：同一用户、同一商品存在 `pv_time <= cart_time <= buy_time` 时记为 1，否则为 0。
- 上述链路均为观察窗口内是否曾出现该关系的用户级 0/1 特征。

### 12.5 用户-商品交互特征

| 特征 | 口径 |
| --- | --- |
| 主键 | `user_id + item_id` |
| 四类交互数 | 用户对商品的 pv/fav/cart/buy 行数 |
| 最近交互 | 该用户-商品组合的 `max(time)` |
| 时间外键 | 从最近交互派生 `last_interaction_date + last_interaction_hour` |
| 是否购买 | 该用户-商品组合 `buy_count >= 1` 为 1 |

### 12.6 商品转化链路特征

- 粒度为 `item_id`，转化行为数与 `item_features` 对应四类行为数逐项一致。
- 包含 `fav/pv`、`cart/pv`、`buy/pv`、`buy/fav`和 `buy/cart` 五类行为次数比，分母为 0 时记为 `0.0`。
- `conversion_has_full_funnel=1` 表示该商品的 pv/fav/cart/buy 计数均大于 0，只表示四阶段均出现，不代表用户级严格时序转化。
- `conversion_features.parquet` 是全局一行的描述性漏斗，不代替商品粒度转化表。

### 12.7 初版特征宽表

- 基表为 `user_item_features.parquet`，最终粒度和主键为 `user_id + item_id`。
- 合并用户、用户序列、商品、类目、最近交互时间、用户-商品交互和商品转化链路特征。
- 初版宽表共 4,686,904 行、82 列；不包含未来标签、样本切分或负采样结果。
- 检查要求：主键唯一、全表无缺失、计数非负、比率有限且非负、0/1 与分类字段合法、不同成员重复计数字段一致。
- 当前质量检查状态为 `PASS`，详见 `reports/stage2_feature_table_report.md`。

## 13. 看板与报告口径

| 项目 | 统一口径 |
| --- | --- |
| 看板数据源 | 只使用当前正式 clean 数据或由其生成的中间表 |
| 看板初版范围 | 数据集概览、行为类型、用户活跃度、商品/类目分布、时间趋势和描述性转化漏斗 |
| 特征看板范围 | 用户活跃度与购买率、商品热度与转化率、类目流量与转化率、行为深度与购买率 |
| 时间标注 | 报告和看板必须说明数据窗口或截止时间 |
| 数值引用 | 报告中的数值必须能追溯到输出表或正式质量报告，不得手工猜测 |
| 比率展示 | 展示时可转为百分比并四舍五入，底层表保留原始比率全精度 |
| 历史结果 | 基于 6,213,379 行旧 clean 数据生成的 EDA 表和结论必须重算后才能用于正式看板与报告 |
| 当前看板状态 | 阶段二分工要求的四张看板 Parquet 表尚未生成，由 `python scr/build_dashboard_data.py` 补齐后再标记完成 |

## 14. 文件命名、输出和复现标准

| 项目 | 统一口径 |
| --- | --- |
| Python 源码 | `src/<module>/snake_case.py` |
| 核心可执行脚本 | 项目拉取后复现核心数据流必须运行的入口放在 `scripts/<verb>_<object>.py` |
| 辅助脚本 | 报告、看板数据等非必跑产物生成入口放在 `scr/<verb>_<object>.py` |
| SQL | 按阶段放入 `sql/preprocessing/`、`sql/basic_analysis/`、`sql/intermediate/` 或 `sql/analysis/` |
| 文档与报告 | 正式口径放 `docs/`，结果报告放 `reports/`，文件名使用英文 snake_case |
| 过程小表 | `data/interim/` |
| 特征大表 | `data/features/` |
| 阶段三标签、特征快照和切分数据 | `data/splits/` |
| 模型 | `models/` |
| 图表和指标 | `outputs/figures/` 和 `outputs/metrics/` |
| 运行方式 | 正式处理必须由 `scripts/` 中的入口执行，不以 Notebook 手工单次运行作为唯一交付 |
| 可复现要求 | 输入路径、观察窗口、参数、输出路径和口径版本必须可查；不依赖未记录的手工步骤 |
| 输出校验 | 大表生成后必须回读并检查列名、类型、行数、主键和核心取值范围 |

## 15. 第三阶段建模口径

### 15.1 样本、目标与时间窗口

| 项目 | 统一口径 |
| --- | --- |
| 数据总范围 | `2025-11-18 00:00:00` 至 `2025-12-18 23:00:00` |
| 样本粒度 | 每个数据集内每个 `user_id + item_id` 一行；标签表保留 `prediction_date` 追踪本批次对应的单日标签窗口 |
| `prediction_date` 字段 | 为兼容当前标签表的字段名，记录该数据集的标签日；训练、验证、测试集分别固定为 `2025-12-08`、`2025-12-15`、`2025-12-18` |
| 候选样本 | 对应观察窗口内至少发生过一次行为的唯一 `user_id + item_id` 组合 |
| 预测目标 | 候选用户—商品对在对应单日标签窗口内是否发生购买行为 |
| 特征 / 预测基准日范围 | 按数据集分别使用下表指定的 20 天、6 天和 2 天历史行为，每个数据集只生成一个特征快照和一个标签日，不在范围内逐日滚动生成样本 |
| 标签窗口 | 对应标签日的 `00:00:00`—`23:59:59`，共 1 个自然日 |
| 正样本 | 候选用户—商品对在预测窗口内存在 `behavior_type=4` 的购买行为，`label=1` |
| 负样本 | 候选用户—商品对在预测窗口内不存在购买行为，`label=0` |
| 时间隔离 | 各数据集的特征只能使用下表指定的特征基准日范围；对应标签日及其后的行为不得参与特征计算 |

本阶段的“未来 1 天”指上述单独的一个自然日标签窗口，不再使用“未来 7 天”口径。阶段二全周期宽表不能直接作为阶段三模型输入；训练、验证、测试特征必须分别在各自的特征基准日范围内重新计算。

### 15.2 训练集、验证集和测试集切分

数据集严格按下表切分，不随机抽样。

| 数据集 | 特征 / 预测基准日 | 标签窗口 | 说明 |
| --- | --- | --- | --- |
| 训练集 | `2025-11-18`—`2025-12-07` | `2025-12-08` | 用前 20 天样本训练，`2025-12-08` 只作为训练标签日 |
| 验证集 | `2025-12-09`—`2025-12-14` | `2025-12-15` | 用 6 天样本验证，`2025-12-15` 只作为验证标签日 |
| 测试集 | `2025-12-16`—`2025-12-17` | `2025-12-18` | 用 2 天样本测试，`2025-12-18` 只作为测试标签日 |

候选用户—商品对和特征均只使用对应行的特征基准日范围生成，标签只使用对应单日标签窗口生成。标签日首次出现、但在对应特征基准日范围中从未出现的用户—商品对不进入当前候选样本，并应在样本构建报告中单独统计。

## 16. 尚未规定的口径

下列内容尚未形成正式决定，不得由个人默认补全：

- 原始数据的可验证外部来源和获取版本。
- 基线模型、候选模型、随机种子和调参方案。
- 类别不平衡处理方式。
- 核心评估指标、分类阈值、排序指标和模型对比规则。
- 预测结果字段、排序和交付格式。
- 模型和预测结果的正式版本号规则。
