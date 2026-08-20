# 项目流程

> 记录格式：做了什么 → 对应文件或数据表路径。

## 修改记录

| 时间 | 修改人 | 版本号 | 备注 |
| --- | --- | --- | --- |
| 2026-08-20 | Member 1 | v1.0 | 完成阶段一项目流程整理 |
| 2026-08-20 | Member 1 | v1.1 | 新增阶段二特征口径、中间表结构和特征字典代码 |
| 2026-08-20 | Member 1 | v1.2 | 完成阶段一产物检查并生成阶段二特征字典与表结构 |
| 2026-08-20 | Member 1 | v1.3 | 完成阶段二用户、商品、类目和时间中间表构建 |

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
- 汇总基础行为统计结果和业务结论 → `reports/member3_data_basic_behavior_statistics.md` （需按当前 clean 口径更新）

### 5. 完整执行顺序

`data/raw/user_behavior_processed.csv` → `scripts/setup_local_database.py` → `scripts/run_user_behavior_cleaning.py` → `sql/basic_analysis/basic_behavior_statistics.sql` → `reports/`

## 阶段二：深度特征工程与探索性分析

### 1. 特征口径与中间表设计

- 统一统计窗口、粒度、时间和转化率口径，并定义用户、商品、类目和时间中间表字段 → `src/features/stage2_feature_specification.py`
- 校验 clean 输入字段并导出特征字典和中间表结构 → `scripts/export_stage2_feature_specification.py`
- 验证主键定义、输入字段和规格文件导出逻辑 → `tests/test_stage2_feature_specification.py`
- 生成用户、商品、类目和时间特征字典 → `data/features/stage2_feature_dictionary.csv`
- 生成四类中间表的主键、粒度和字段结构 → `data/features/stage2_intermediate_table_schemas.json`
- 从 clean Parquet 构建四类中间表并执行主键、类型和总量对账 → `src/features/stage2_intermediate_tables.py`
- 提供四类中间表的全量构建入口 → `scripts/build_stage2_intermediate_tables.py`
- 验证小样聚合、特征比率和输出对账 → `tests/test_stage2_intermediate_tables.py`
- 生成 10,000 行用户维度中间表 → `data/features/user_features.parquet`
- 生成 2,876,947 行商品维度中间表 → `data/features/item_features.parquet`
- 生成 8,916 行类目维度中间表 → `data/features/category_features.parquet`
- 生成 744 行日期-小时维度中间表 → `data/features/time_features.parquet`
