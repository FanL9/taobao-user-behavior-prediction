from pathlib import Path
import json

import pandas as pd


USER_PATH = Path("data/features/user_features.parquet")
TIME_PATH = Path("data/features/time_features.parquet")
SEQ_PATH = Path("data/features/user_sequence_features.parquet")

REPORT_PATH = Path("outputs/member2_stage2_feature_validation.json")


def check_binary(df, cols):
    result = {}
    for col in cols:
        vals = sorted(df[col].dropna().unique().tolist())
        result[col] = {
            "unique_values": vals,
            "valid": set(vals).issubset({0, 1}),
        }
    return result


def main():
    user = pd.read_parquet(USER_PATH)
    time_df = pd.read_parquet(TIME_PATH)
    seq = pd.read_parquet(SEQ_PATH)

    report = {
        "user_features": {
            "shape": list(user.shape),
            "duplicate_user_id": int(user["user_id"].duplicated().sum()),
            "null_user_id": int(user["user_id"].isna().sum()),
            "required_columns_present": all(
                c in user.columns
                for c in [
                    "user_avg_daily_behavior_count",
                    "user_activity_level",
                    "user_behavior_span_hours",
                    "user_recency_hours",
                ]
            ),
            "negative_avg_daily_count": int(
                (user["user_avg_daily_behavior_count"] < 0).sum()
            ),
            "negative_behavior_span": int(
                (user["user_behavior_span_hours"] < 0).sum()
            ),
            "invalid_activity_level": int(
                (~user["user_activity_level"].isin(["high", "low"])).sum()
            ),
        },
        "time_features": {
            "shape": list(time_df.shape),
            "duplicate_key": int(
                time_df.duplicated(
                    ["behavior_date", "behavior_hour"]
                ).sum()
            ),
            "required_columns_present": all(
                c in time_df.columns
                for c in [
                    "weekday",
                    "is_weekend",
                    "time_period",
                ]
            ),
            "invalid_weekend_flag": int(
                (~time_df["is_weekend"].isin([0, 1])).sum()
            ),
            "invalid_time_period": int(
                (
                    ~time_df["time_period"].isin(
                        ["night", "morning", "afternoon", "evening"]
                    )
                ).sum()
            ),
        },
        "sequence_features": {
            "shape": list(seq.shape),
            "duplicate_user_id": int(seq["user_id"].duplicated().sum()),
            "null_user_id": int(seq["user_id"].isna().sum()),
            "required_columns_present": all(
                c in seq.columns
                for c in [
                    "sequence_recent_10_behavior_types",
                    "sequence_avg_behavior_gap_hours",
                    "sequence_has_pv_cart",
                    "sequence_has_pv_fav",
                    "sequence_has_pv_buy",
                    "sequence_has_pv_cart_buy",
                ]
            ),
            "max_sequence_length": int(
                seq["sequence_recent_10_behavior_types"]
                .apply(len)
                .max()
            ),
            "empty_sequence_count": int(
                (
                    seq["sequence_recent_10_behavior_types"]
                    .apply(len)
                    == 0
                ).sum()
            ),
            "invalid_behavior_value_count": int(
                sum(
                    any(v not in (1, 2, 3, 4) for v in x)
                    for x in seq["sequence_recent_10_behavior_types"]
                )
            ),
            "negative_gap_count": int(
                (seq["sequence_avg_behavior_gap_hours"] < 0).sum()
            ),
            "null_gap_count": int(
                seq["sequence_avg_behavior_gap_hours"].isna().sum()
            ),
            "binary_flags": check_binary(
                seq,
                [
                    "sequence_has_pv_cart",
                    "sequence_has_pv_fav",
                    "sequence_has_pv_buy",
                    "sequence_has_pv_cart_buy",
                ],
            ),
        },
    }

    report["cross_table_checks"] = {
        "user_count_user_features": int(user["user_id"].nunique()),
        "user_count_sequence_features": int(seq["user_id"].nunique()),
        "same_user_count": (
            user["user_id"].nunique()
            == seq["user_id"].nunique()
        ),
        "same_user_set": (
            set(user["user_id"])
            == set(seq["user_id"])
        ),
    }

    failures = []

    if report["user_features"]["duplicate_user_id"] != 0:
        failures.append("duplicate user_id in user_features")

    if report["user_features"]["null_user_id"] != 0:
        failures.append("null user_id in user_features")

    if not report["user_features"]["required_columns_present"]:
        failures.append("missing required user feature columns")

    if report["user_features"]["negative_avg_daily_count"] != 0:
        failures.append("negative average daily behavior count")

    if report["user_features"]["negative_behavior_span"] != 0:
        failures.append("negative user behavior span")

    if report["user_features"]["invalid_activity_level"] != 0:
        failures.append("invalid user activity level")

    if report["time_features"]["duplicate_key"] != 0:
        failures.append("duplicate time feature key")

    if not report["time_features"]["required_columns_present"]:
        failures.append("missing required time feature columns")

    if report["time_features"]["invalid_weekend_flag"] != 0:
        failures.append("invalid weekend flag")

    if report["time_features"]["invalid_time_period"] != 0:
        failures.append("invalid time period")

    if report["sequence_features"]["duplicate_user_id"] != 0:
        failures.append("duplicate user_id in sequence features")

    if report["sequence_features"]["null_user_id"] != 0:
        failures.append("null user_id in sequence features")

    if not report["sequence_features"]["required_columns_present"]:
        failures.append("missing required sequence feature columns")

    if report["sequence_features"]["max_sequence_length"] > 10:
        failures.append("sequence longer than 10")

    if report["sequence_features"]["empty_sequence_count"] != 0:
        failures.append("empty recent sequence")

    if report["sequence_features"]["invalid_behavior_value_count"] != 0:
        failures.append("invalid behavior value in sequence")

    if report["sequence_features"]["negative_gap_count"] != 0:
        failures.append("negative sequence gap")

    if report["sequence_features"]["null_gap_count"] != 0:
        failures.append("null sequence gap")

    for name, info in report["sequence_features"]["binary_flags"].items():
        if not info["valid"]:
            failures.append(f"invalid binary values in {name}")

    if not report["cross_table_checks"]["same_user_count"]:
        failures.append("user count mismatch between user and sequence tables")

    if not report["cross_table_checks"]["same_user_set"]:
        failures.append("user set mismatch between user and sequence tables")

    report["status"] = "PASS" if not failures else "FAIL"
    report["failures"] = failures

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(json.dumps(report, ensure_ascii=False, indent=2))
    print()
    print("STATUS =", report["status"])

    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
