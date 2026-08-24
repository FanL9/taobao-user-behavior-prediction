# Member 2 Stage 3 Modeling Sample Report

## 1. Task Scope

Member 2 is responsible for preparing the model-ready user-item samples for Stage 3, including:

* constructing user-item modeling samples;
* generating future 7-day purchase labels;
* splitting train / validation / test datasets by time;
* rebuilding features based only on information available before each cutoff;
* preprocessing model features;
* excluding identifiers, future-window metadata, and leakage-prone raw fields;
* auditing the final model-ready datasets before handing them to Member 1.

The final prediction task is:

> Given historical behavior up to the prediction cutoff, predict whether a specific `user_id + item_id` pair will generate a purchase within the following 7 days.

## 2. Sample Granularity and Target

Sample key:

```text
user_id + item_id
```

Target column:

```text
label
```

Label definition:

```text
label = 1
```

if the user purchases the corresponding item within the future 7-day prediction window.

```text
label = 0
```

otherwise.

`user_id` and `item_id` remain sample identifiers and are not included in the traditional machine-learning feature matrix.

## 3. Final Model-Ready Files

The final model-ready datasets are generated locally and are not uploaded to GitHub.

```text
data/modeling/train/train_model_ready.parquet
data/modeling/valid/valid_model_ready.parquet
data/modeling/test/test_model_ready.parquet
```

Current audited dataset sizes:

| Split |      Rows | Positive Samples | Negative Samples | Positive Rate |
| ----- | --------: | ---------------: | ---------------: | ------------: |
| Train | 1,459,489 |            2,924 |        1,456,565 |     0.200344% |
| Valid | 2,507,302 |            3,243 |        2,504,059 |     0.129342% |
| Test  | 3,574,665 |            9,315 |        3,565,350 |     0.260584% |

The purchase-prediction task is therefore highly imbalanced. Member 1 should not rely on Accuracy alone when evaluating model quality.

## 4. Model Feature Set

Each model-ready dataset contains:

```text
107 total columns
104 model features
```

The remaining columns are sample identifiers and the target.

The final feature set covers the following major groups:

* user-item interaction features;
* user behavior and activity features;
* item behavior and popularity features;
* category behavior and popularity features;
* conversion-chain features;
* user behavior sequence features;
* time-period and weekday features;
* engineered recency and interaction-time features.

The final model feature list is stored in:

```text
configs/stage3_model_feature_list.txt
```

Feature configuration is stored in:

```text
configs/stage3_feature_config.json
```

## 5. Leakage Control

The Stage 3 feature pipeline follows the prediction-window isolation rule.

Main controls include:

* features are calculated only from behavior available at or before each split cutoff;
* the future 7-day label window is used only for label generation;
* `cutoff_time`, `label_start`, and `label_end` are metadata and are not model features;
* raw `user_id` and `item_id` remain sample keys rather than traditional model features;
* raw `category_id` is excluded as an integer identifier while category aggregate features remain;
* raw datetime fields are excluded after engineered time and recency features are generated;
* train / validation / test datasets use a consistent model feature schema.

## 6. Final Audit Result

The final audit script is:

```text
scripts/audit_stage3_model_ready.py
```

Audit reports:

```text
reports/stage3_model_ready_audit.json
reports/stage3_model_ready_audit.md
```

Current audit result:

```text
Overall status: PASS
Schema consistency: True
Model feature count: 104
```

For all three splits:

* duplicate sample keys: 0;
* feature null values: 0;
* feature NaN values: 0;
* feature infinite values: 0;
* constant features: 0;
* forbidden leakage columns: none;
* label validation: PASS.

## 7. Handover to Member 1

Member 1 can use the following files directly for baseline model training:

```text
data/modeling/train/train_model_ready.parquet
data/modeling/valid/valid_model_ready.parquet
data/modeling/test/test_model_ready.parquet
```

Recommended loading logic:

```python
import pandas as pd

train = pd.read_parquet("data/modeling/train/train_model_ready.parquet")
valid = pd.read_parquet("data/modeling/valid/valid_model_ready.parquet")
test = pd.read_parquet("data/modeling/test/test_model_ready.parquet")

feature_cols = [
    line.strip()
    for line in open("configs/stage3_model_feature_list.txt", encoding="utf-8")
    if line.strip()
]

X_train = train[feature_cols]
y_train = train["label"]

X_valid = valid[feature_cols]
y_valid = valid["label"]

X_test = test[feature_cols]
y_test = test["label"]
```

Member 1 can then proceed with:

```text
Logistic Regression
Random Forest
XGBoost
LightGBM
```

Because the positive class is highly imbalanced, model training should compare class weighting and other imbalance-handling strategies. Validation and test evaluation should focus especially on ROC-AUC, PR-AUC / Average Precision, Precision, Recall and F1 rather than Accuracy alone.

## 8. Stage 3 Member 2 Status

Current Member 2 core Stage 3 modeling-data tasks are considered completed:

```text
Modeling sample construction        DONE
Future 7-day label generation       DONE
Time-based dataset split            DONE
Feature reconstruction              DONE
Feature preprocessing               DONE
Final model feature list            DONE
Leakage control                     DONE
Model-ready audit                   PASS
Member 1 training-data handover     READY
```

Large model-ready Parquet files remain local and are not uploaded to GitHub.
