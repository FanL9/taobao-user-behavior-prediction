# 淘宝用户行为预测

本项目基于用户浏览、收藏、加购和购买行为，完成数据治理、EDA 和特征工程，为后续购买预测做准备。

## 核心数据流

```text
data/raw/user_behavior_processed.csv
    → data/processed/user_behavior_clean.parquet
    → data/features/{user,item,category,time,user_item}_features.parquet
    → data/features/user_sequence_features.parquet
    → data/features/item_conversion_features.parquet
    → data/features/user_item_feature_table.parquet
```

阶段二的权威输入是：

```text
data/processed/user_behavior_clean.parquet
```

## 行为映射

| 值 | 行为 |
| ---: | --- |
| 1 | 浏览 `pv` |
| 2 | 收藏 `fav` |
| 3 | 加购 `cart` |
| 4 | 购买 `buy` |

`time` 仅精确到小时，普通重复行为保留；同一 `user_id + item_id + behavior_type + time` 达到 60 次及以上时，才按异常高频组折叠为一条。

## 运行

```bash
python -m pip install -r requirements.txt
python scripts/setup_local_database.py
python scripts/run_user_behavior_cleaning.py --output-parquet
python scripts/build_stage2_intermediate_tables.py
python scripts/build_member2_stage2_features.py
python scripts/build_member3_stage2_features.py
python scripts/build_stage2_feature_table.py
```

### 可视化看板

看板不属于当前阶段二完成范围；需要本地预览现有页面时运行：

```bash
python scr/build_dashboard_data.py
streamlit run dashboards/app.py
```


## 阶段二已生成中间表

| 文件 | 粒度 | 主键 |
| --- | --- | --- |
| `data/features/user_features.parquet` | 每用户一行 | `user_id` |
| `data/features/item_features.parquet` | 每商品一行 | `item_id` |
| `data/features/category_features.parquet` | 每类目一行 | `category_id` |
| `data/features/time_features.parquet` | 每日每小时一行 | `behavior_date + behavior_hour` |
| `data/features/user_sequence_features.parquet` | 每用户一行 | `user_id` |
| `data/features/user_item_features.parquet` | 每用户-商品一行 | `user_id + item_id` |
| `data/features/item_conversion_features.parquet` | 每商品一行 | `item_id` |
| `data/features/conversion_features.parquet` | 全局一行 | `conversion_scope` |
| `data/features/user_item_feature_table.parquet` | 每用户-商品一行 | `user_id + item_id` |

Member 2/3 的非看板特征、转化表和初版宽表已生成并通过质量检查。

## Git 约定

- `data/raw/`、`data/processed/` 和 `database/` 中的大文件不上传。
- `user_item_features.parquet` 和 `user_item_feature_table.parquet` 仅本地生成，不上传。
- `data/features/` 中其他特征文件可按 Git 规则上传。
- 大文件的本地准备和生成方式见 `docs/local_large_files.md`。
- 代码、SQL、文档和报告可上传。

## 文档

- 全项目统一口径：`docs/project_definition.md`
- 项目交付流程：`docs/project_workflow.md`
- 本地大文件准备：`docs/local_large_files.md`
- 数据质量报告：`reports/member2_data_quality_report.md`
- Member 2 阶段二报告：`reports/member2_stage2_feature_report.md`
- Member 3 阶段二报告：`reports/member3_stage2_feature_report.md`
- 初版特征宽表报告：`reports/stage2_feature_table_report.md`
