# 本地数据与表格交付清单

本文件同时记录两类产物：

1. 因体积较大或含本地数据而不上传 GitHub 的文件；
2. 阶段一、阶段二分工中要求的全部 CSV / Parquet 表格交付，包括可上传的小表。

不能只根据文件大小判断是否属于阶段交付。标记为“仅本地”的文件已由 `.gitignore` 排除；标记为“Git”的小表可正常提交。

## 1. 仅本地保存的源数据、数据库和大表

| 本地文件 | 当前大致大小 | 本地准备或生成方式 |
| --- | ---: | --- |
| `data/raw/user_behavior_processed.csv` | 469 MB | 手动将原始数据集放到该路径 |
| `data/raw/user_behavior_processed.parquet` | 118 MB | `python scripts/setup_local_database.py` |
| `database/taobao_user_behavior.db` | 2.1 GB | `python scripts/setup_local_database.py` |
| `data/processed/user_behavior_clean.csv` | 当前未生成 | `python scripts/run_user_behavior_cleaning.py`；仅需要 CSV 时生成 |
| `data/processed/user_behavior_clean.parquet` | 139 MB | `python scripts/run_user_behavior_cleaning.py --output-parquet` |
| `data/interim/item_statistics.csv` | 52 MB | 阶段一基础 EDA 流程 |
| `data/features/user_item_features.parquet` | 50 MB | `python scripts/build_stage2_intermediate_tables.py` |
| `data/features/user_item_feature_table.parquet` | 225 MB | `python scripts/build_stage2_feature_table.py` |

`user_item_features.parquet` 虽未超过 GitHub 100 MB 的单文件限制，但它可由脚本稳定重建，因此与初版特征宽表一样仅本地保留。

## 2. 阶段一 CSV / Parquet 交付总表

| 输出 | 内容 | Git 策略 | 生成方式 |
| --- | --- | --- | --- |
| `data/processed/user_behavior_clean.csv` | 标准清洗数据 CSV | 仅本地 | `python scripts/run_user_behavior_cleaning.py` |
| `data/processed/user_behavior_clean.parquet` | 标准清洗数据 Parquet | 仅本地 | `python scripts/run_user_behavior_cleaning.py --output-parquet` |
| `data/interim/behavior_distribution.csv` | 四类行为分布 | Git | 阶段一基础 EDA 流程 |
| `data/interim/behavior_statistics.csv` | 用户与行为核心统计 | Git | 阶段一基础 EDA 流程 |
| `data/interim/item_statistics.csv` | 商品行为统计 | 仅本地 | 阶段一基础 EDA 流程 |
| `data/interim/top_10_item.csv` | 热门商品 Top 10 | Git | 阶段一基础 EDA 流程 |
| `data/interim/category_statistics.csv` | 类目行为统计 | Git | 阶段一基础 EDA 流程 |
| `data/interim/top_10_category.csv` | 热门类目 Top 10 | Git | 阶段一基础 EDA 流程 |
| `data/interim/daily_behavior.csv` | 日粒度行为量 | Git | 阶段一基础 EDA 流程 |
| `data/interim/hourly_behavior.csv` | 小时粒度行为量 | Git | 阶段一基础 EDA 流程 |
| `data/interim/behavior_hourly_distribution.csv` | 不同行为类型的小时分布 | Git | 阶段一基础 EDA 流程 |
| `data/interim/descriptive_funnel.csv` | 描述性转化漏斗 | Git | 阶段一基础 EDA 流程 |

阶段一分工中的“数据规模、缺失值、异常值、重复值、清洗前后对比表”当前汇总在 `reports/member2_data_quality_report.md` 中，没有另拆为多个 CSV。`outputs/user_behavior_cleaning_report.json` 是已废弃的旧口径结果，不得作为当前交付。

## 3. 阶段二 CSV / Parquet 交付总表

### 3.1 正式特征表

| 输出 | 粒度 / 内容 | Git 策略 | 生成方式 |
| --- | --- | --- | --- |
| `data/features/user_features.parquet` | 每用户一行；用户行为与活跃度特征 | Git | `python scripts/build_stage2_intermediate_tables.py` |
| `data/features/time_features.parquet` | 每日每小时一行；时间特征 | Git | `python scripts/build_stage2_intermediate_tables.py` |
| `data/features/user_sequence_features.parquet` | 每用户一行；用户序列特征 | Git | `python scripts/build_member2_stage2_features.py` |
| `data/features/item_features.parquet` | 每商品一行；商品行为与热度特征 | Git | `python scripts/build_stage2_intermediate_tables.py` |
| `data/features/category_features.parquet` | 每类目一行；类目行为与热度特征 | Git | `python scripts/build_stage2_intermediate_tables.py` |
| `data/features/user_item_features.parquet` | 每用户—商品一行；交互特征 | 仅本地 | `python scripts/build_stage2_intermediate_tables.py` |
| `data/features/item_conversion_features.parquet` | 每商品一行；商品转化链路特征 | Git | `python scripts/build_member3_stage2_features.py` |
| `data/features/conversion_features.parquet` | 全局一行；描述性转化漏斗 | Git | `python scripts/build_member3_stage2_features.py` |
| `data/features/user_item_feature_table.parquet` | 每用户—商品一行；阶段二初版宽表 | 仅本地 | `python scripts/build_stage2_feature_table.py` |

### 3.2 补充旧口径 CSV

下列 CSV 已有产物，但字段定义与正式 Parquet 不完全相同，不作为最终特征宽表输入。

| 输出 | Git 策略 | 生成方式 |
| --- | --- | --- |
| `data/features/user_active_level.csv` | Git | `python scr/build_legacy_member2_csv_features.py` |
| `data/features/time_feature_hourly_weekly.csv` | Git | `python scr/build_legacy_member2_csv_features.py` |
| `data/features/peak_hour_features.csv` | Git | `python scr/build_legacy_member2_csv_features.py` |
| `data/features/user_sequence_features.csv` | Git | `python scr/build_legacy_member2_csv_features.py` |

### 3.3 EDA 看板数据表

阶段二分工明确要求 EDA 看板和第二阶段特征看板数据。下列四张表由 `python scr/build_dashboard_data.py` 生成，目前尚未在 `data/features/dashboard/` 中生成，属于待生成交付。

| 输出 | 内容 | Git 策略 |
| --- | --- | --- |
| `data/features/dashboard/item_conversion_analysis.parquet` | 商品热度与转化 | 仅本地 |
| `data/features/dashboard/category_conversion_analysis.parquet` | 类目流量与转化 | 仅本地 |
| `data/features/dashboard/user_behavior_depth.parquet` | 用户行为深度与购买 | 仅本地 |
| `data/features/dashboard/conversion_funnel.parquet` | 转化漏斗 | 仅本地 |

### 3.4 校验与报告产物

| 输出 | 状态 / 说明 |
| --- | --- |
| `outputs/member2_stage2_feature_validation.json` | 现有 Member 2 特征校验结果，`outputs/` 仅本地 |
| `outputs/member3_stage2_feature_validation.json` | 现有 Member 3 特征校验结果，`outputs/` 仅本地 |
| `outputs/stage2_feature_table_validation.json` | `python scripts/build_stage2_feature_table.py` 自动生成，仅本地 |
| `reports/member2_stage2_feature_report.md` | Member 2 正式特征说明与质量检查 |
| `reports/member3_stage2_feature_report.md` | Member 3 正式特征说明与质量检查 |
| `reports/stage2_feature_table_report.md` | 初版特征宽表说明与检查 |

## 4. 阶段一、二本地生成顺序

```text
在本地放置 data/raw/user_behavior_processed.csv
    → python scripts/setup_local_database.py
    → python scripts/run_user_behavior_cleaning.py --output-parquet
    → 运行阶段一基础 EDA 流程
    → python scripts/build_stage2_intermediate_tables.py
    → python scripts/build_member2_stage2_features.py
    → python scripts/build_member3_stage2_features.py
    → python scripts/build_stage2_feature_table.py
    → python scr/build_dashboard_data.py
```

## 5. 阶段三本地建模文件

阶段三大规模样本、快照特征、标签和最终入模数据均保存在 `data/modeling/` 并由 `.gitignore` 排除。

| 本地输出 | 说明 |
| --- | --- |
| `data/modeling/train_labels.parquet` | 训练集标签，标签日 `2025-12-08` |
| `data/modeling/valid_labels.parquet` | 验证集标签，标签日 `2025-12-15` |
| `data/modeling/test_labels.parquet` | 测试集标签，标签日 `2025-12-18` |
| `data/modeling/purchase_labels.parquet` | 训练、验证、测试合并标签表，粒度为 `user_id + item_id + prediction_date` |
| `data/modeling/purchase_label_summary.csv` | 三个数据集的特征日范围、标签日、正负样本数和正样本率 |
| `data/modeling/<split>/snapshots/<label_date>/features/*.parquet` | 各数据集按其特征基准日范围重算的用户、商品、类目、时间、序列和用户—商品快照特征 |
| `data/modeling/train/train_modeling.parquet` | 训练集建模样本 |
| `data/modeling/valid/valid_modeling.parquet` | 验证集建模样本 |
| `data/modeling/test/test_modeling.parquet` | 测试集建模样本 |
| `data/modeling/train/train_model_ready.parquet` | 训练集最终入模数据 |
| `data/modeling/valid/valid_model_ready.parquet` | 验证集最终入模数据 |
| `data/modeling/test/test_model_ready.parquet` | 测试集最终入模数据 |

阶段三的时间切分、标签窗口和时间泄露规则以 `docs/project_definition.md` 第 15 节为唯一权威口径。

Member 2 第 1、3 部分统一生成与审计命令：

```text
python scripts/build_stage3_samples_and_labels.py
```

审计结果保存为 `reports/stage3_samples_and_labels_audit.json` 和 `reports/stage3_samples_and_labels_audit.md`。
