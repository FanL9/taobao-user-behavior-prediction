# Stage 3 特征预处理与筛选

## 输入与目标

Stage 3 预测历史交互 user-item 在下一自然日是否购买。`prediction_date` 是特征截止日，所有特征只能使用当日 `23:59:59` 及以前的信息；标签窗口固定为 `[prediction_date + 1 day, prediction_date + 2 days)`。

唯一预处理输入为：

```text
data/modeling/train/train_modeling.parquet
data/modeling/valid/valid_modeling.parquet
data/modeling/test/test_modeling.parquet
```

不得使用阶段二全观察窗宽表或旧的非 snapshot Stage 3 特征目录替代。

## 字段角色

- Sample key：`user_id`、`item_id`、`prediction_date`。
- Tracking：`user_id`、`item_id`、`category_id`、`prediction_date`。
- Target：`label`。
- Metadata：`cutoff_time`、`label_start`、`label_end`。
- Model features：经过泄露排除、预处理和 train-only 筛选后保留的数值列。

Tracking、target、metadata、原始时间戳以及匹配 target/future/label-window 规则的字段均不得进入 `X`。

## Fit/transform 生命周期

```text
deterministic train-only fit sample
    → Stage3Preprocessor.fit(train)
    → Stage3FeatureSelector.fit(X_train)
    → freeze state
    → transform(train)
    → transform(valid)
    → transform(test)
```

Valid/test 不得更新 fill value、类别集合、clipping 边界、scaler、缺失率、方差、相关性或选中特征清单。拟合样本策略、样本数、随机种子和源数据行数写入 preprocessor state。

## 预处理规则

1. Count/event-count 字段缺失填 `0`。
2. 类别缺失和未见类别映射到显式 `__UNKNOWN__`，one-hot 输出列由 train 冻结。
3. 其他数值字段使用 train median。
4. 异常值策略可关闭或使用 train 分位数 clipping；禁止删除样本。
5. tree profile 不进行 scaling。
6. linear profile 使用 train-fitted `StandardScaler`，不强制缩放 one-hot/binary 字段。
7. 最近行为位置暂时保持数值编码以兼容现有 schema，未来是否 one-hot 由配置扩展。

Snapshot 中的 `user_activity_level`、商品/类目热度分层和 Peak-hour P80 会在 valid/test 横截面重新计算，因此当前从最终 `X` 排除；模型继续使用对应的原始 count 特征。

## 特征筛选规则

筛选器依次使用 train 规则处理：

1. 高缺失率；
2. 常量、近常量 binary 和低方差连续特征；
3. 高相关数值特征。

高相关 tie-break 顺序为：配置 whitelist、较低缺失率、配置名称前缀优先级、稳定字典序。已知 item count 与 conversion count 的完全重复关系由通用相关规则识别，不使用专门硬编码删除。

每个删除记录包含：

```text
feature
reason
statistic
threshold
paired_feature
fit_split
```

## 大数据约束

正式 train 约数千万行，`build_stage3_model_ready.py` 不会一次性载入全部数据：

- 使用按 sample key 的 seeded hash，从所有 train batch 中确定性保留固定上限的拟合样本；
- train-only 样本拟合全部状态；
- train/valid/test 按 Arrow batch 转换并写出；
- 所有 split 使用相同 selected feature schema。

正式数据尚未准备完整时，只运行小型 `unittest`，不运行全量构建，不生成正式 model-ready Parquet、feature-selection report 或 preprocessor artifact。
