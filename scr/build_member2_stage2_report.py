"""Build the optional Member 2 stage-two feature report."""

from pathlib import Path
import pandas as pd

USER_PATH = Path("data/features/user_features.parquet")
TIME_PATH = Path("data/features/time_features.parquet")
SEQ_PATH = Path("data/features/user_sequence_features.parquet")
REPORT_PATH = Path("reports/member2_stage2_feature_report.md")


def u(s):
    """Return text unchanged; source file is already UTF-8."""
    return s

def main():
    user = pd.read_parquet(USER_PATH)
    time_df = pd.read_parquet(TIME_PATH)
    seq = pd.read_parquet(SEQ_PATH)

    sequence_flags = [
        "sequence_has_pv_cart",
        "sequence_has_pv_fav",
        "sequence_has_pv_buy",
        "sequence_has_pv_cart_buy",
    ]
    validation_passed = (
        not user["user_id"].isna().any()
        and not user["user_id"].duplicated().any()
        and not time_df.duplicated(["behavior_date", "behavior_hour"]).any()
        and time_df["time_is_peak_hour"].isin([0, 1]).all()
        and not seq["user_id"].isna().any()
        and not seq["user_id"].duplicated().any()
        and seq["sequence_recent_10_behavior_types"].apply(len).le(10).all()
        and seq[sequence_flags].isin([0, 1]).all().all()
        and set(user["user_id"]) == set(seq["user_id"])
    )

    activity_counts = (
        user["user_activity_level"]
        .value_counts()
        .to_dict()
    )

    weekend_counts = (
        time_df["is_weekend"]
        .value_counts()
        .to_dict()
    )

    period_counts = (
        time_df["time_period"]
        .value_counts()
        .to_dict()
    )

    peak_hours = sorted(
        time_df.loc[time_df["time_is_peak_hour"] == 1, "behavior_hour"]
        .astype(int)
        .unique()
        .tolist()
    )

    chain_cols = [
        "sequence_has_pv_cart",
        "sequence_has_pv_fav",
        "sequence_has_pv_buy",
        "sequence_has_pv_cart_buy",
    ]

    chain_counts = {
        c: int(seq[c].sum())
        for c in chain_cols
    }

    report = f"""# Member 2 \u9636\u6bb5\u4e8c\u7279\u5f81\u5de5\u7a0b\u62a5\u544a

## 1. \u5de5\u4f5c\u8303\u56f4

\u672c\u9636\u6bb5\u5b8c\u6210 Member 2 \u8d1f\u8d23\u7684\u7528\u6237\u884c\u4e3a\u7279\u5f81\u3001\u7528\u6237\u6d3b\u8dc3\u5ea6\u7279\u5f81\u3001\u65f6\u95f4\u7279\u5f81\u548c\u7528\u6237\u884c\u4e3a\u5e8f\u5217\u7279\u5f81\uff0c\u5e76\u5bf9\u6700\u7ec8\u7279\u5f81\u8868\u8fdb\u884c\u8d28\u91cf\u68c0\u67e5\u3002

\u9636\u6bb5\u4e8c\u4e0d\u8bad\u7ec3\u6a21\u578b\uff0c\u4e5f\u4e0d\u751f\u6210\u672a\u6765\u8d2d\u4e70\u6807\u7b7e\u3002

## 2. \u7528\u6237\u7279\u5f81

- \u8f93\u51fa\u6587\u4ef6\uff1a`data/features/user_features.parquet`
- \u8868\u89c4\u6a21\uff1a{user.shape[0]:,} \u884c x {user.shape[1]} \u5217
- \u4e3b\u952e\uff1a`user_id`
- \u6bcf\u7528\u6237\u4e00\u884c

\u672c\u6b21\u8865\u5145\u5b57\u6bb5\uff1a

- `user_avg_daily_behavior_count`
- `user_activity_level`
- `user_behavior_span_hours`

\u53e3\u5f84\uff1a

- \u65e5\u5747\u884c\u4e3a\u6570 = `user_total_count / user_active_day_count`
- \u6d3b\u8dc3\u5206\u5c42\uff1a\u7528\u6237\u603b\u884c\u4e3a\u6570\u5927\u4e8e\u7b49\u4e8e\u5168\u4f53\u7528\u6237\u4e2d\u4f4d\u6570\u65f6\u4e3a `high`\uff0c\u5426\u5219\u4e3a `low`
- \u884c\u4e3a\u65f6\u95f4\u8de8\u5ea6 = \u7528\u6237\u6700\u8fd1\u884c\u4e3a\u65f6\u95f4\u4e0e\u9996\u6b21\u884c\u4e3a\u65f6\u95f4\u4e4b\u5dee\uff0c\u5355\u4f4d\u4e3a\u5c0f\u65f6

\u6d3b\u8dc3\u5206\u5c42\u5206\u5e03\uff1a

- high: {activity_counts.get("high", 0):,}
- low: {activity_counts.get("low", 0):,}

## 3. \u65f6\u95f4\u7279\u5f81

- \u8f93\u51fa\u6587\u4ef6\uff1a`data/features/time_features.parquet`
- \u8868\u89c4\u6a21\uff1a{time_df.shape[0]:,} \u884c x {time_df.shape[1]} \u5217
- \u7c92\u5ea6\uff1a`behavior_date + behavior_hour`

\u672c\u6b21\u8865\u5145\u5b57\u6bb5\uff1a

- `is_weekend`
- `time_period`
- `time_is_peak_hour`

`is_weekend` \u4f7f\u7528 `weekday >= 5` \u5224\u5b9a\u5468\u672b\u3002

`time_period` \u5206\u4e3a\uff1a

- night: 00:00-05:59
- morning: 06:00-11:59
- afternoon: 12:00-17:59
- evening: 18:00-23:59

\u65f6\u95f4\u7279\u5f81\u7edf\u8ba1\uff1a

- \u5de5\u4f5c\u65e5\u5c0f\u65f6\u8bb0\u5f55\uff1a{weekend_counts.get(0, 0):,}
- \u5468\u672b\u5c0f\u65f6\u8bb0\u5f55\uff1a{weekend_counts.get(1, 0):,}
- night: {period_counts.get("night", 0):,}
- morning: {period_counts.get("morning", 0):,}
- afternoon: {period_counts.get("afternoon", 0):,}
- evening: {period_counts.get("evening", 0):,}
- \u9ad8\u5cf0\u5c0f\u65f6\uff08\u5c0f\u65f6\u603b\u884c\u4e3a\u91cf >= P80\uff09: {", ".join(map(str, peak_hours))}

## 4. \u7528\u6237\u884c\u4e3a\u5e8f\u5217\u7279\u5f81

- \u8f93\u51fa\u6587\u4ef6\uff1a`data/features/user_sequence_features.parquet`
- \u8868\u89c4\u6a21\uff1a{seq.shape[0]:,} \u884c x {seq.shape[1]} \u5217
- \u4e3b\u952e\uff1a`user_id`
- \u6bcf\u7528\u6237\u4e00\u884c

\u5b57\u6bb5\uff1a

- `sequence_recent_10_behavior_types`
- `sequence_avg_behavior_gap_hours`
- `sequence_has_pv_cart`
- `sequence_has_pv_fav`
- `sequence_has_pv_buy`
- `sequence_has_pv_cart_buy`

\u7531\u4e8e\u539f\u59cb\u65f6\u95f4\u53ea\u7cbe\u786e\u5230\u5c0f\u65f6\uff0c\u540c\u4e00\u5c0f\u65f6\u5185\u7684\u771f\u5b9e\u884c\u4e3a\u987a\u5e8f\u65e0\u6cd5\u6062\u590d\u3002\u4e3a\u4fdd\u8bc1\u53ef\u590d\u73b0\u6027\uff0c\u6309 `time, item_id, behavior_type` \u8fdb\u884c\u786e\u5b9a\u6027\u6392\u5e8f\uff0c\u56e0\u6b64\u8be5\u5e8f\u5217\u5e94\u89c6\u4e3a\u8fd1\u4f3c\u5e8f\u5217\u3002

\u6700\u8fd1\u884c\u4e3a\u5e8f\u5217\u7edf\u4e00\u4fdd\u7559\u6700\u8fd1 10 \u4e2a `behavior_type`\u3002

\u94fe\u8def\u7279\u5f81\u5728\u540c\u4e00\u7528\u6237\u3001\u540c\u4e00\u5546\u54c1\u5185\u5224\u5b9a\uff1a

- PV -> Cart: {chain_counts["sequence_has_pv_cart"]:,} \u7528\u6237
- PV -> Fav: {chain_counts["sequence_has_pv_fav"]:,} \u7528\u6237
- PV -> Buy: {chain_counts["sequence_has_pv_buy"]:,} \u7528\u6237
- PV -> Cart -> Buy: {chain_counts["sequence_has_pv_cart_buy"]:,} \u7528\u6237

## 5. \u8d28\u91cf\u68c0\u67e5

\u8d28\u91cf\u68c0\u67e5\u5305\u62ec\uff1a

- \u4e3b\u952e\u7f3a\u5931\u4e0e\u91cd\u590d\u68c0\u67e5
- \u5fc5\u9700\u5b57\u6bb5\u5b58\u5728\u6027\u68c0\u67e5
- \u6570\u503c\u975e\u8d1f\u6027\u68c0\u67e5
- \u6d3b\u8dc3\u5206\u5c42\u5408\u6cd5\u503c\u68c0\u67e5
- \u5468\u672b\u6807\u8bb0\u548c\u65f6\u6bb5\u5408\u6cd5\u503c\u68c0\u67e5
- \u5e8f\u5217\u957f\u5ea6\u4e0d\u8d85\u8fc7 10
- \u884c\u4e3a\u7c7b\u578b\u53ea\u5141\u8bb8 1/2/3/4
- \u94fe\u8def\u6807\u8bb0\u53ea\u5141\u8bb8 0/1
- `user_features` \u4e0e `user_sequence_features` \u7528\u6237\u6570\u548c\u7528\u6237\u96c6\u5408\u4e00\u81f4

\u8d28\u91cf\u68c0\u67e5\u7531\u6b63\u5f0f\u7279\u5f81\u6784\u5efa\u4ee3\u7801\u548c\u672c\u62a5\u544a\u751f\u6210\u811a\u672c\u76f4\u63a5\u6267\u884c\uff0c\u4e0d\u518d\u7ef4\u62a4\u72ec\u7acb\u6821\u9a8c\u811a\u672c\u3002

VALIDATION STATUS = {"PASS" if validation_passed else "FAIL"}

### 5.1 \u68c0\u67e5\u8fb9\u754c

\u4e0a\u8ff0 `PASS` \u8868\u793a\u6b63\u5f0f\u7684\u7528\u6237\u3001\u65f6\u95f4\u548c\u5e8f\u5217 Parquet \u8868\u901a\u8fc7\u6821\u9a8c\u3002`user_active_level.csv`\u3001`time_feature_hourly_weekly.csv`\u3001`peak_hour_features.csv` \u548c `user_sequence_features.csv` \u4e3a\u8865\u5145\u65e7\u53e3\u5f84\u4ea7\u7269\uff0c\u4e0d\u4f5c\u4e3a\u540e\u7eed\u5bbd\u8868\u7684\u6b63\u5f0f\u8f93\u5165\u3002

## 6. \u6700\u7ec8\u4ea4\u4ed8

Member 2 \u9636\u6bb5\u4e8c\u7684\u7528\u6237\u3001\u65f6\u95f4\u548c\u5e8f\u5217\u6838\u5fc3 Parquet \u8868\u53ca\u8d28\u91cf\u9a8c\u8bc1\u5df2\u5b8c\u6210\u3002

\u6700\u7ec8\u4ea4\u4ed8\u7269\uff1a

- `data/features/user_features.parquet`
- `data/features/time_features.parquet`
- `data/features/user_sequence_features.parquet`
- `scripts/build_member2_stage2_features.py`
- `reports/member2_stage2_feature_report.md`

VALIDATION STATUS = {"PASS" if validation_passed else "FAIL"}

MEMBER2_CORE_TABLES_READY = {"YES" if validation_passed else "NO"}

FINAL STATUS = {"PASS" if validation_passed else "FAIL"}
"""

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(
        u(report),
        encoding="utf-8",
        newline="\n",
    )

    print("REPORT REBUILD SUCCESS")
    print("Report:", REPORT_PATH)
    print("User shape:", user.shape)
    print("Time shape:", time_df.shape)
    print("Sequence shape:", seq.shape)


if __name__ == "__main__":
    main()
