# 本地数据设置

## 文件与路径约定

本项目原始输入文件名固定为：

```text
user_behavior_processed.csv
```

本地生成的原始 Parquet 文件名固定为：

```text
user_behavior_processed.parquet
```

两个文件都放在：

```text
data/raw/
```

SQLite 数据库路径为：

```text
database/taobao_user_behavior.db
```

SQLite 原始表名固定为 `user_behavior_processed`。

## 使用规则

- 原始 CSV 是项目的数据来源文件，不直接修改。
- Parquet 是原始数据的高效读取副本，用于后续 Python 检查、清洗、EDA 和建模。
- SQLite 数据库仅用于 SQL 验证和 DBeaver 查看。
- CSV、Parquet 和 SQLite 数据库等大型数据文件均不上传 GitHub。
- 本地初始化统一运行 `python scripts/setup_local_database.py`。
