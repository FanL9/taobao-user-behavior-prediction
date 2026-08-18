# Member 2 数据质量与清洗处理报告

本报告依据 `outputs/user_behavior_cleaning_report.json` 中的全量运行结果编制。报告中的指标均来自该 JSON；比例和行数对账仅进行确定性算术换算。

## 1. 数据说明

- 输入文件：`data/raw/user_behavior_processed.csv`
- CSV 输出：`data/processed/user_behavior_clean.csv`
- Parquet 输出：`data/processed/user_behavior_clean.parquet`
- 数据时间范围：`2025-11-18 00:00:00` 至 `2025-12-18 23:00:00`
- 原始数据规模：12,256,906 条记录

## 2. 数据质量检查

### 2.1 基础规模

| 检查项 | 结果 |
| --- | ---: |
| 唯一用户数 | 10,000 |
| 唯一商品数 | 2,876,947 |
| 唯一类目数 | 8,916 |

### 2.2 行为类型分布

| `behavior_type` | `behavior_name` | 记录数 |
| ---: | --- | ---: |
| 1 | `pv` | 11,550,581 |
| 2 | `fav` | 242,556 |
| 3 | `cart` | 343,564 |
| 4 | `buy` | 120,205 |

四类行为记录数合计为 12,256,906，与原始总记录数一致。

### 2.3 缺失值检查

| 字段 | 缺失记录数 |
| --- | ---: |
| `time` | 0 |
| `user_id` | 0 |
| `item_id` | 0 |
| `item_category` | 0 |
| `behavior_type` | 0 |

存在至少一个关键字段缺失的记录数为 0。

### 2.4 非法值与时间格式检查

| 检查项 | 问题记录数 |
| --- | ---: |
| 非法 `behavior_type` | 0 |
| 非法 ID（任一 ID 字段） | 0 |
| 非法 `user_id` | 0 |
| 非法 `item_id` | 0 |
| 非法 `item_category` | 0 |
| 无法解析的 `time` | 0 |

时间采用严格的 `%Y-%m-%d %H` 格式解析，未额外设置日期合法区间。

## 3. 重复数据检查

| 检查项 | 重复记录数 |
| --- | ---: |
| 完全重复记录 | 6,043,527 |
| `user_id + item_id + behavior_type + time` 四元组重复记录 | 6,043,527 |

清洗去重键定义为：

```text
user_id + item_id + behavior_type + time
```

去重在全量数据范围内执行，同一去重键保留首次出现的记录，删除其后重复记录，能够识别跨读取分块的重复。

本次完全重复记录数与四元组重复记录数完全相同。结合两项统计可知，本次四元组重复没有因 `item_category` 不同而产生额外重复；相同四元组对应的其他原始字段也一致。因此，按四元组删除的 6,043,527 条记录同时属于完全重复记录。

## 4. 数据清洗规则

1. `behavior_type` 按统一口径映射：

   | `behavior_type` | `behavior_name` |
   | ---: | --- |
   | 1 | `pv` |
   | 2 | `fav` |
   | 3 | `cart` |
   | 4 | `buy` |

2. 将 `item_category` 标准化为 `category_id`。
3. 按 `%Y-%m-%d %H` 严格解析 `time`，不使用人为设定的时间合法区间。
4. 从 `time` 生成：
   - `behavior_date`：行为日期；
   - `behavior_hour`：行为发生小时；
   - `weekday`：星期编号，星期一为 0，星期日为 6。
5. ID 必须为非空正整数，并能使用现有 `Int64` / SQLite `INTEGER` 表示；不设置项目未定义的业务 ID 范围。
6. 删除关键字段缺失、非法行为类型、非法 ID 和无法解析时间的记录。
7. 按 `user_id + item_id + behavior_type + time` 实施全局去重，避免仅在单个 chunk 内去重造成跨 chunk 重复残留。

## 5. 清洗前后对比

| 指标 | 数量或比例 |
| --- | ---: |
| 原始记录数 | 12,256,906 |
| 清洗后记录数 | 6,213,379 |
| 实际删除记录数 | 6,043,527 |
| 删除比例 | 49.307117% |
| 存在关键字段缺失的记录数 | 0 |
| 非法行为类型记录数 | 0 |
| 非法 ID 记录数 | 0 |
| 无法解析时间记录数 | 0 |
| 完全重复记录数 | 6,043,527 |
| 四元组重复记录数 | 6,043,527 |

质量问题数量可能发生重叠，因此不能直接将各项问题数相加作为删除总数。本次互斥删除原因统计如下：

| 互斥删除原因 | 实际删除记录数 |
| --- | ---: |
| 关键字段缺失 | 0 |
| 非法行为类型 | 0 |
| 非法 ID | 0 |
| 无法解析时间 | 0 |
| 四元组重复 | 6,043,527 |
| **合计** | **6,043,527** |

## 6. 清洗结果验证

- 清洗后四元组重复数：0。该结果由 JSON 中“四元组重复记录数 6,043,527”与“实际按重复键删除 6,043,527 条”严格推导。
- 行数对账：`12,256,906 - 6,043,527 = 6,213,379`，与 JSON 中的清洗后记录数完全一致。
- `reconciled` 状态：`true`。
- CSV 输出：`data/processed/user_behavior_clean.csv`。
- Parquet 输出：`data/processed/user_behavior_clean.parquet`。

## 7. 性能信息

- 全量清洗耗时：451.187 秒，约 7 分 31.187 秒。

## 8. 后续使用说明

Member 3 应使用以下 clean 数据开展 EDA：

```text
data/processed/user_behavior_clean.csv
```

或：

```text
data/processed/user_behavior_clean.parquet
```

`data/raw/user_behavior_processed.csv` 是阶段一输入数据，不是最终 clean 数据。后续 EDA、图表和最终统计结论不应直接基于 processed 输入数据生成，以免重复记录导致行为量、用户活跃度和转化相关指标被重复累计。
