# 淘宝用户行为预测

本项目用于淘宝用户行为预测。

## 仓库与数据约定

GitHub 仓库只保存脚本、SQL、文档、配置文件和小型统计结果。

原始 CSV 文件约 469MB，超过 GitHub 普通文件上传限制，因此不上传。Parquet 和 SQLite 数据库均由成员在本地生成，也不上传。

组员 clone 仓库后，需要自行获取原始 CSV，并放到固定路径：

```text
data/raw/user_behavior_processed.csv
```

推荐的本地数据库文件路径为：

```text
database/taobao_user_behavior.db
```

当前输入表名为 `user_behavior_processed`。推荐的原始导入表名为 `user_behavior_processed` 或 `user_behavior_raw`。如果原始文件名为 `user_behavior_processed.csv`，但它仍是项目输入数据，可以先作为阶段一输入表使用。

## 数据字段

当前表字段包括：

- `time`
- `user_id`
- `item_id`
- `item_category`
- `behavior_type`

`behavior_type` 映射：

| 值 | 行为 |
| --- | --- |
| 1 | 浏览（pv） |
| 2 | 收藏（fav） |
| 3 | 加购（cart） |
| 4 | 购买（buy） |

## 本地使用流程

1. Clone 本仓库。
2. 获取原始 CSV，并放到 `data/raw/user_behavior_processed.csv`。
3. 安装依赖：

   ```bash
   python -m pip install -r requirements.txt
   ```

4. 运行一键初始化脚本：

   ```bash
   python scripts/setup_local_database.py
   ```

   脚本以分块方式读取大 CSV，并生成：

   ```text
   data/raw/user_behavior_processed.parquet
   database/taobao_user_behavior.db
   ```

   SQLite 原始表名固定为 `user_behavior_processed`。完成数据处理后，脚本还会自动执行：

   1. `sql/preprocessing/00_create_base_indexes.sql`
   2. `sql/preprocessing/01_create_behavior_mapping_view.sql`

5. Parquet 或 SQLite 原始表已存在时，脚本默认复用，不会覆盖。确认需要全部重建时可运行：

   ```bash
   python scripts/setup_local_database.py --parquet-if-exists replace --if-exists replace
   ```

6. 导入完成后，可使用 `sql/preprocessing/02_basic_data_status_check.sql` 检查实际数据状态。
7. 后续 Python 大表检查、清洗、EDA 和建模优先读取 Parquet；SQLite 数据库主要用于 DBeaver、SQL 验证和映射视图查询。
8. 后续 SQL 分析优先使用视图 `vw_user_behavior_mapped`，不直接修改输入表。

CSV、Parquet 和 SQLite 数据库都只保留在本地，不提交到 GitHub。
