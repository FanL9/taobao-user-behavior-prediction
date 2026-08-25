# Member 2 阶段三建模样本与标签构建报告

## 1. 任务范围

本次完成 Member 2 的两部分交付：

1. 基于分窗口重算的阶段二特征构建建模样本；
2. 构建单日购买标签，并检查标签、时间窗口与未来信息。

原根目录临时文件 `temp.py` 已移除，正式统一入口为：

```text
python scripts/build_stage3_samples_and_labels.py
```

该入口依次生成标签、基础特征快照、序列特征、建模样本和审计报告，不依赖个人桌面路径。

## 2. 时间口径

| 数据集 | 特征 / 预测基准日 | 标签日 | 特征原始行为数 |
| --- | --- | --- | ---: |
| train | `2025-11-18`—`2025-12-07` | `2025-12-08` | 7,506,554 |
| valid | `2025-12-09`—`2025-12-14` | `2025-12-15` | 2,809,856 |
| test | `2025-12-16`—`2025-12-17` | `2025-12-18` | 779,876 |

每个数据集只生成一个特征快照和一个单日标签窗口，不在特征日范围内逐日滚动生成样本。

## 3. 购买标签

每个数据集内以 `user_id + item_id` 为样本主键，标签表保留 `prediction_date` 追踪标签日。候选用户—商品对在标签日购买该商品记为 `label=1`，否则记为 `label=0`。

| 数据集 | 样本数 | 正样本 | 负样本 | 正样本率 | 错标 / 漏标 |
| --- | ---: | ---: | ---: | ---: | ---: |
| train | 2,944,576 | 895 | 2,943,681 | 0.030395% | 0 |
| valid | 1,110,131 | 886 | 1,109,245 | 0.079810% | 0 |
| test | 329,938 | 616 | 329,322 | 0.186702% | 0 |

正式输出：

```text
data/modeling/train_labels.parquet
data/modeling/valid_labels.parquet
data/modeling/test_labels.parquet
data/modeling/purchase_labels.parquet
data/modeling/purchase_label_summary.csv
```

### 3.1 标签日首次出现的购买对

候选集只包含对应特征基准日范围内出现过的用户—商品对，因此标签日首次出现的购买对不进入当前候选集。

| 数据集 | 标签日全部购买对 | 被排除的新购买对 |
| --- | ---: | ---: |
| train | 2,997 | 2,102 |
| valid | 3,301 | 2,415 |
| test | 3,151 | 2,535 |

这是候选集适用范围，不是错标。模型结论中必须说明当前模型不覆盖标签日首次出现的用户—商品对。

## 4. 建模样本特征

三个建模样本均为 87 列，已关联下列八类特征：

- 用户—商品交互特征；
- 用户基础行为特征；
- 用户活跃度特征；
- 时间特征；
- 用户行为序列特征；
- 商品行为与热度特征；
- 类目行为与热度特征；
- `item_id` 粒度的商品转化链路特征。

全局单行 `conversion_features.parquet` / `conversion_scope` 没有拼入建模样本。

正式输出：

```text
data/modeling/train/train_modeling.parquet
data/modeling/valid/valid_modeling.parquet
data/modeling/test/test_modeling.parquet
```

## 5. 未来信息与完整性审计

审计入口：

```text
python scripts/build_stage3_samples_and_labels.py --audit-only
```

审计结果：`PASS`。

| 数据集 | 用户—商品最后交互最大时间 | 用户最后行为最大时间 | 未来时间字段 | 缺失值 |
| --- | --- | --- | ---: | ---: |
| train | `2025-12-07 23:00:00` | `2025-12-07 23:00:00` | 0 | 0 |
| valid | `2025-12-14 23:00:00` | `2025-12-14 23:00:00` | 0 | 0 |
| test | `2025-12-17 23:00:00` | `2025-12-17 23:00:00` | 0 | 0 |

同时通过以下检查：

- 标签值仅为 0/1；
- 标签表和建模样本均无主键重复；
- 建模样本与对应标签表的主键和标签完全一致；
- 八类要求特征全部存在；
- 建模样本无缺失值；
- 未将全局单行转化率拼入宽表。

详细结果：

```text
reports/stage3_samples_and_labels_audit.json
reports/stage3_samples_and_labels_audit.md
```

## 6. 交付状态

```text
Member 2 第 1 部分：建模样本构建       PASS
Member 2 第 3 部分：购买预测标签构建   PASS
时间窗口隔离                          PASS
未来信息审计                          PASS
建模样本与标签一致性                PASS
```

本报告不代表 Member 2 第 5 部分“特征预处理 / model-ready”已按新口径完成。旧的 `stage3_model_ready_audit` 仍保持 `INVALIDATED`，需在完成第 5 部分后重新生成。
