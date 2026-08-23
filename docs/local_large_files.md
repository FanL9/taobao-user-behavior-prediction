# 本地大文件说明

下列文件因体积较大，不上传至 GitHub。项目成员在运行对应流程前，需要在本地手动准备或通过脚本重新生成。

| 本地文件 | 当前大致大小 | 本地准备方式 |
| --- | ---: | --- |
| `data/raw/user_behavior_processed.csv` | 469 MB | 手动将原始数据集放到该路径。 |
| `data/raw/user_behavior_processed.parquet` | 118 MB | 运行 `python scripts/setup_local_database.py`。 |
| `database/taobao_user_behavior.db` | 2.1 GB | 运行 `python scripts/setup_local_database.py`。 |
| `data/processed/user_behavior_clean.parquet` | 139 MB | 运行 `python scripts/run_user_behavior_cleaning.py --output-parquet`。 |
| `data/processed/user_behavior_clean.csv` | 当前不存在，预计体积较大 | 仅在需要 CSV 格式时运行 `python scripts/run_user_behavior_cleaning.py`；阶段二统一以 Parquet 文件作为正式输入。 |
| `data/interim/item_statistics.csv` | 52 MB | 通过阶段一基础分析流程在本地重新生成。 |
| `data/features/user_item_features.parquet` | 50 MB | 运行 `python scripts/build_stage2_intermediate_tables.py`。 |
| `data/features/user_item_feature_table.parquet` | 225 MB | 阶段二各类特征输入准备完成后，运行 `python scripts/build_stage2_feature_table.py`。 |

`user_item_features.parquet` 虽然未超过 GitHub 的 100 MB 单文件限制，但由于文件较大且可以通过脚本重新生成，因此仍只保留在本地。初版特征宽表超过 GitHub 的常规单文件大小限制，也必须保留在本地。

## 其他生成文件

下列文件不是项目源数据，需要时应在本地重新生成。`outputs/` 目录中的校验 JSON 文件不会上传；看板数据不属于当前阶段二的完成范围。

| 本地输出 | 本地生成方式 |
| --- | --- |
| `outputs/stage2_feature_table_validation.json` | 运行 `python scripts/build_stage2_feature_table.py` 时自动生成。 |

## 本地执行顺序

```text
在本地放置 data/raw/user_behavior_processed.csv
    → python scripts/setup_local_database.py
    → python scripts/run_user_behavior_cleaning.py --output-parquet
    → python scripts/build_stage2_intermediate_tables.py
    → python scripts/build_member2_stage2_features.py
    → python scripts/build_member3_stage2_features.py
    → python scripts/build_stage2_feature_table.py
```

中间表构建命令会重新生成用户、商品、类目、时间以及仅保存在本地的用户—商品交互特征表。Member 2 特征构建命令会重新生成正式的用户序列特征表。被 `.gitignore` 忽略的文件应继续保留在本地，不要使用 `git add -f` 强制添加。
