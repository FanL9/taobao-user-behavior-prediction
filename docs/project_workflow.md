# 项目流程

> 记录格式：做了什么 → 对应文件或数据表路径。

## 修改记录

| 时间 | 修改人 | 版本号 | 备注 |
| --- | --- | --- | --- |
| 2026-08-20 | Member 1 | v1.0 | 完成阶段一项目流程整理 |
| 2026-08-20 | Member 1 | v1.1 | 新增阶段二特征口径和中间表设计 |
| 2026-08-20 | Member 1 | v1.2 | 完成阶段一产物检查 |
| 2026-08-20 | Member 1 | v1.3 | 完成阶段二用户、商品、类目和时间中间表构建 |
| 2026-08-20 | Member 1 | v1.4 | 同步统一口径、项目流程和精简 README |
| 2026-08-20 | Member 1 | v1.5 | 删除独立规格代码和字典输出，特征口径统一收口到 `project_definition.md` |
| 2026-08-20 | Member 1 | v1.6 | 新增用户-商品交互特征表 |
| 2026-08-23 | Member 1 | v1.7 | 补充 Member 2/3 阶段二交付、校验结果和未完成项 |
| 2026-08-23 | Member 1 | v1.8 | 完成高峰、热度、转化特征、Member 2/3 校验和 82 列初版宽表 |
| 2026-08-25 | Member 1 | v1.9 | 补全阶段一、二表格交付清单，明确阶段二看板数据待生成，统一阶段三固定时间切分 |
| 2026-08-25 | Member 1 | v1.10 | 完成阶段三 Member 2 第 1、3 部分固定窗口样本、标签、特征快照和未来信息审计 |

## 阶段一：数据接入、基础治理与初步 EDA

### 1. 项目与数据口径

- 定义项目目标、预测对象和阶段划分 → `docs/project_definition.md`
- 说明原始数据、Parquet 和 SQLite 的本地准备方式 → `docs/data_setup.md`
- 记录输入数据的基础状态和字段口径 → `docs/basic_data_check.md`
- 说明仓库结构、行为映射和本地运行流程 → `README.md`

### 2. 数据接入与数据库

- 提供项目运行所需的 Python 依赖清单 → `requirements.txt`
- 保存阶段一的原始输入数据 → `data/raw/user_behavior_processed.csv`
- 分块导入 CSV，并生成 Parquet、SQLite 原始表、索引和映射视图 → `scripts/setup_local_database.py`
- 生成便于 Python 读取的原始 Parquet 表 → `data/raw/user_behavior_processed.parquet`
- 生成本地 SQLite 数据库 → `database/taobao_user_behavior.db`
- 在 SQLite 中保存导入后的原始行为表 → `database/taobao_user_behavior.db` 中的 `user_behavior_processed`
- 为用户、商品、类目、行为和时间字段建立基础索引 → `sql/preprocessing/00_create_base_indexes.sql`
- 将 1/2/3/4 行为类型映射为 pv/fav/cart/buy → `sql/preprocessing/01_create_behavior_mapping_view.sql`
- 在 SQLite 中提供统一的行为映射视图 → `database/taobao_user_behavior.db` 中的 `vw_user_behavior_mapped`
- 检查数据量、字段、时间范围和行为类型 → `sql/preprocessing/02_basic_data_status_check.sql`

### 3. 数据质量检查与清洗

- 实现分块读取、质量检查、重复诊断、异常高频处理和字段标准化 → `src/data/user_behavior_cleaning_pipeline.py`
- 提供清洗流程的命令行入口并组织输出 → `scripts/run_user_behavior_cleaning.py`
- 验证清洗规则、去重、字段类型和输出一致性 → `tests/test_clean_user_behavior.py`
- 为清洗自动化测试提供小型输入样本 → `tests/fixtures/user_behavior_sample.csv`
- 生成标准清洗 CSV 表 → `data/processed/user_behavior_clean.csv`
- 生成标准清洗 Parquet 表 → `data/processed/user_behavior_clean.parquet`
- 保留旧版全量去重结果供历史追溯，不作为当前口径 → `outputs/user_behavior_cleaning_report.json` （已废弃）
- 汇总数据质量问题、处理规则和清洗结果 → `reports/member2_data_quality_report.md`

### 4. 基础行为统计与 EDA

- 统计行为、用户、商品、类目、时间和转化漏斗 → `sql/basic_analysis/basic_behavior_statistics.sql`
- 输出四类行为的数量与占比表 → `data/interim/behavior_distribution.csv`
- 输出总行为、购买、购买用户、未购买用户和复购用户统计表 → `data/interim/behavior_statistics.csv`
- 输出每个商品的浏览、收藏、加购和购买次数表 → `data/interim/item_statistics.csv`
- 输出购买次数前 10 的热门商品表 → `data/interim/top_10_item.csv`
- 输出类目行为量、购买量和购买占比表 → `data/interim/category_statistics.csv`
- 输出购买次数前 10 的热门类目表 → `data/interim/top_10_category.csv`
- 输出按日期汇总的行为量表 → `data/interim/daily_behavior.csv`
- 输出按小时汇总的行为量表 → `data/interim/hourly_behavior.csv`
- 输出各小时四类行为的分布表 → `data/interim/behavior_hourly_distribution.csv`
- 输出浏览、收藏、加购和购买的描述性漏斗表 → `data/interim/descriptive_funnel.csv`
- 汇总基础行为统计结果和业务结论 → `reports/member3_stage1_data_basic_behavior_statistics_report.md`

### 5. 完整执行顺序

`data/raw/user_behavior_processed.csv` → `scripts/setup_local_database.py` → `scripts/run_user_behavior_cleaning.py` → `sql/basic_analysis/basic_behavior_statistics.sql` → `reports/`

## 阶段二：深度特征工程与探索性分析

### 1. 特征口径与中间表设计

- 阶段二基础中间表均直接基于 `data/processed/user_behavior_clean.parquet` 构建
- 统计窗口、粒度、字段、主键和转化率统一口径 → `docs/project_definition.md`
- 从 clean Parquet 构建基础中间表并执行主键、类型和总量对账 → `src/features/stage2_intermediate_tables.py`
- 提供阶段二中间表的全量构建入口 → `scripts/build_stage2_intermediate_tables.py`
- 验证小样聚合、特征比率和输出对账 → `tests/test_stage2_intermediate_tables.py`
- 生成 10,000 行用户维度中间表 → `data/features/user_features.parquet`
- 生成 2,876,947 行商品维度中间表 → `data/features/item_features.parquet`
- 生成 8,916 行类目维度中间表 → `data/features/category_features.parquet`
- 生成 744 行日期-小时维度中间表 → `data/features/time_features.parquet`
- 按 `user_id + item_id` 生成 4,686,904 行四类交互数、最近交互时间和购买标记 → `data/features/user_item_features.parquet`

### 2. Member 2：用户、时间与序列特征

- 在基础构建中补充用户日均行为、高低活跃分层和行为跨度 → `src/features/stage2_intermediate_tables.py`
- 在时间表中补充工作日/周末、时段和 P80 高峰小时特征 → `src/features/stage2_intermediate_tables.py`
- 按用户构建最近 10 次行为、平均间隔和同商品转化链路标记 → `scripts/build_member2_stage2_features.py`
- 生成 10,000 行用户特征表 → `data/features/user_features.parquet`
- 生成 744 行日期-小时特征表 → `data/features/time_features.parquet`
- 生成 10,000 行用户序列特征表 → `data/features/user_sequence_features.parquet`
- 用户、时间和序列构建代码内置主键、必需字段、数值范围和序列合法性检查，当前状态为 `PASS`
- 汇总正式 Member 2 口径、结果和质量检查 → `reports/member2_stage2_feature_report.md`

补充产物 `user_active_level.csv`、`time_feature_hourly_weekly.csv`、`peak_hour_features.csv` 和 `user_sequence_features.csv` 使用了与正式 Parquet 不同的 P20/P80、N=5 及相邻转移口径，因此不作为后续宽表的正式输入。正式高峰小时特征已写入 `time_features.parquet`。

### 3. Member 3：商品、类目与转化特征

- 生成 2,876,947 行商品特征表，并按 Q25/Q75 写入热度分层 → `data/features/item_features.parquet`
- 生成 8,916 行类目特征表，并按 Q25/Q75 写入热门/长尾分层 → `data/features/category_features.parquet`
- 从商品特征构建商品粒度和全局转化特征 → `src/features/conversion_features.py`
- 提供 Member 3 非看板特征构建入口 → `scripts/build_member3_stage2_features.py`
- 生成 2,876,947 行商品转化链路表 → `data/features/item_conversion_features.parquet`
- 生成 1 行全局描述性转化漏斗 → `data/features/conversion_features.parquet`
- 转化特征构建代码内置主键、分层、比率、商品集合和跨表总量检查，当前状态为 `PASS`
- 记录 Member 3 非看板特征口径、结果和质量检查 → `reports/member3_stage2_feature_report.md`

### 4. Member 1：初版特征宽表整合

- 以用户-商品交互表为基表，左连接用户、序列、商品、类目、时间和转化特征 → `src/features/stage2_feature_table.py`
- 提供宽表构建和自动校验入口 → `scripts/build_stage2_feature_table.py`
- 生成 4,686,904 行、82 列初版特征宽表 → `data/features/user_item_feature_table.parquet`
- 检查主键、全表缺失、计数、比率、标记、分类和成员输出一致性，当前状态为 `PASS` → `outputs/stage2_feature_table_validation.json`
- 记录宽表来源、连接方式和质量结果 → `reports/stage2_feature_table_report.md`

### 5. 当前执行顺序

```text
data/processed/user_behavior_clean.parquet
    → python scripts/build_stage2_intermediate_tables.py
    → python scripts/build_member2_stage2_features.py
    → python scripts/build_member3_stage2_features.py
    → python scripts/build_stage2_feature_table.py
```

阶段二分工要求的四张看板 Parquet 表由 `scr/build_dashboard_data.py` 生成；当前 `data/features/dashboard/` 中尚未生成这四张表，待补齐后再将看板数据交付标记为完成。

### 6. 辅助产物生成

`scr/` 中的脚本不是复现核心数据流的必跑步骤，只在需要刷新报告或看板数据时运行：

```text
python scr/build_member2_stage2_report.py
python scr/build_member3_stage2_report.py
python scr/build_stage2_feature_table_report.py
python scr/build_dashboard_data.py
```

## 阶段三：Member 2 建模样本与标签

- 根据固定 20 天 / 6 天 / 2 天特征窗口构建候选用户—商品对。
- 使用 `2025-12-08`、`2025-12-15`、`2025-12-18` 单日购买行为生成标签。
- 分别重算用户、活跃度、时间、序列、商品、类目、用户—商品和商品转化链路特征。
- 统一入口 → `scripts/build_stage3_samples_and_labels.py`。
- 生成三个 87 列建模样本 → `data/splits/<split>/<split>_modeling.parquet`。
- 生成合并标签与汇总 → `data/splits/purchase_labels.parquet` 和 `data/splits/purchase_label_summary.csv`。
- 通过同一必跑入口的 `--audit-only` 参数检查主键、标签、特征组、缺失值、全局转化表误拼接和未来时间 → `python scripts/build_stage3_samples_and_labels.py --audit-only`。
- 审计结果为 `PASS` → `reports/stage3_samples_and_labels_audit.md`。
