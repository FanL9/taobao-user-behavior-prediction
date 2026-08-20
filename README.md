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
7. 后续 SQL 分析优先使用视图 `vw_user_behavior_mapped`，不直接修改输入表。

## Member 2：标准数据清洗

标准清洗入口：

```bash
python scripts/run_user_behavior_cleaning.py --output-parquet
```

默认输入：

```text
data/raw/user_behavior_processed.csv
```

默认输出：

```text
data/processed/user_behavior_clean.csv
data/processed/user_behavior_clean.parquet
reports/member2_data_quality_report.md
```

### 重复行为处理口径

输入数据的 `time` 只精确到小时。因此同一用户可能在同一小时内对同一商品真实发生多次浏览、收藏、加购或购买，不能把相同 `user_id + item_id + behavior_type + time` 一律当作错误重复并删除。

当前规则为：

- 四元组相同但出现次数低于 60：全部保留；
- 同一四元组在同一小时内出现 **60 次及以上**：标记为异常高频/疑似恶意重复组；
- 对异常高频组只保留第一条，其余记录删除；
- 阈值为包含边界，即 60 次正好触发。

需要特别说明：由于源数据没有分钟或秒级时间戳，当前代码**无法判断“一分钟内 60 次”**。因此使用“同一小时内同一四元组达到 60 次”作为当前数据条件下的可执行代理规则。如果后续拿到更细粒度时间戳，应升级为真实滚动时间窗口检测。

可调整阈值：

```bash
python scripts/run_user_behavior_cleaning.py --suspicious-repeat-threshold 60 --output-parquet
```

### 时间合法范围

如项目有明确业务合法时间范围，可配置：

```bash
python scripts/run_user_behavior_cleaning.py \
  --allowed-start "2025-11-18 00" \
  --allowed-end "2025-12-18 23" \
  --output-parquet
```

如果不配置，程序只做严格 `%Y-%m-%d %H` 格式解析并报告实际观测到的最小/最大时间，不会把观测范围自动当成业务合法边界。

### 输出验证

清洗流程使用两遍分块读取：

1. 第一遍统计数据质量和全局四元组重复次数；
2. 第二遍执行清洗，保留正常重复，只折叠达到阈值的异常高频组。

正式文件替换前，程序会重新读取临时 clean CSV（以及可选 Parquet）并验证：

- 字段结构；
- 关键字段无缺失；
- ID 合法；
- `behavior_type` 与 `behavior_name` 一致；
- 时间可解析；
- `behavior_date`、`behavior_hour`、`weekday` 一致；
- clean 行数与清洗统计一致；
- 正常重复可以存在；
- 不允许任何四元组在 clean 数据中仍达到异常高频阈值；
- Parquet 与 CSV 行数、字段一致。

验证通过后才会替换正式输出文件。

### 正式报告

正式 Markdown 报告：

```text
reports/member2_data_quality_report.md
```

报告会明确区分：

- “重复记录统计”——诊断指标，不再等同于删除量；
- “异常高频组”——达到阈值的可疑组；
- “异常高频实际删除行数”——每个可疑组保留一条后的删除量。

因此旧版报告中“所有四元组重复全部删除”的口径已经废弃。修改规则后必须重新全量清洗并重新生成报告，旧版 clean 行数和删除比例不能继续作为最终结论。

### 报告口径说明

正式报告使用仓库相对路径，不写入个人电脑的绝对路径。未配置 `--allowed-start` / `--allowed-end` 时，报告中的“超出合法时间范围”显示为“未配置/不适用”，而不是 0，以区分“未执行范围检查”和“已检查且发现 0 条”。

## Git 提交约定

以下本地大文件不提交到 GitHub：

```text
data/raw/*.csv
data/raw/*.parquet
data/processed/*.csv
data/processed/*.parquet
database/*.db
```

正式 Markdown 报告 `reports/member2_data_quality_report.md` 可以提交 Git。CSV、Parquet 和 SQLite 数据库只保留在本地。
