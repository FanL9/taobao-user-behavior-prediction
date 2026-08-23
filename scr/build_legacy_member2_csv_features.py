### Member 2 补充旧口径 CSV：用户行为、时间与序列特征

# 注意：本文件保留 P20/P80、N=5 和相邻转移的补充分析口径。
# 正式阶段二 Parquet 以 src/features/stage2_intermediate_tables.py 和
# scripts/build_member2_stage2_features.py 为准，本脚本输出不用于后续特征宽表。

#### 负责内容

# 1. 构建用户基础行为特征：
# 用户总行为次数；
# 用户浏览次数；
# 用户收藏次数；
# 用户加购次数；
# 用户购买次数；
# 用户购买转化率。
# 详见 user_features.parquet 中 user_id, user_total_count, user_pv_count, user_fav_count, user_cart_count, user_buy_count, user_fav_to_pv_rate, user_cart_to_pv_rate, user_buy_to_pv_rate



# 2. 构建用户活跃度特征：
# 活跃天数；
# 日均行为次数；
# 最近活跃时间；
# 用户行为时间跨度；
# 高活跃 / 低活跃分层。
# High = total_behavior_count ≥ P80
# Medium = P20 ≤ total_behavior_count < P80
# Low = total_behavior_count < P20
# 产出：user_active_level.csv
import pandas as pd
df = pd.read_parquet(
    "data/features/user_features.parquet"
)
active_days = df["user_active_day_count"]
df["avg_daily_behavior"] = (
    df["user_total_count"] / df["user_active_day_count"]
).round(2)
df["last_active_time"] = df["user_last_behavior_time"]
df["behavior_span_days"] = (
    df["user_last_behavior_time"] - df["user_first_behavior_time"]
).dt.total_seconds() / (24 * 60 * 60)
df["behavior_span_days"] = df["behavior_span_days"].round(2)
p20 = df["user_total_count"].quantile(0.20)
p80 = df["user_total_count"].quantile(0.80)
df["activity_level"] = "Medium"
df.loc[
    df["user_total_count"] < p20,
    "activity_level"
] = "Low"
df.loc[
    df["user_total_count"] >= p80,
    "activity_level"
] = "High"
result = df[
    [
        "user_id",
        "user_active_day_count",
        "avg_daily_behavior",
        "last_active_time",
        "behavior_span_days",
        "activity_level"
    ]
].copy()
result = result.rename(columns={
    "user_active_day_count": "active_days"
})
result.to_csv(
    "data/features/user_active_level.csv",
    index=False
)



# 3. 构建时间特征：
# 小时行为分布；
# 星期行为分布；
# 工作日 / 周末行为差异；
# 高峰时段行为特征。
# Peak = 小时总行为量 ≥ P80
# Non-Peak = 小时总行为量 < P80
# 产出：time_feature_hourly_weekly.csv
# 产出：peak_hour_features.csv
import pandas as pd
df = pd.read_parquet(
     "data/processed/user_behavior_clean.parquet"
)
df["time"] = pd.to_datetime(df["time"])
df["hour"] = df["time"].dt.hour
df["weekday_num"] = df["time"].dt.weekday
weekday_map = {
    0: "Monday",
    1: "Tuesday",
    2: "Wednesday",
    3: "Thursday",
    4: "Friday",
    5: "Saturday",
    6: "Sunday"
}
df["weekday"] = df["weekday_num"].map(weekday_map)
df["day_type"] = df["weekday_num"].apply(
    lambda x: "Weekday" if x < 5 else "Weekend"
)
def create_time_summary(data, group_col, time_dimension):
    result = (
        data.groupby(group_col)
        .agg(
            behavior_count=("behavior_name", "size"),
            pv_count=("behavior_name", lambda x: (x == "pv").sum()),
            fav_count=("behavior_name", lambda x: (x == "fav").sum()),
            cart_count=("behavior_name", lambda x: (x == "cart").sum()),
            buy_count=("behavior_name", lambda x: (x == "buy").sum())
        )
        .reset_index()
    )
    result = result.rename(
        columns={group_col: "time_value"}
    )
    result.insert(
        0,
        "time_dimension",
        time_dimension
    )
    return result
hour_features = create_time_summary(
    df,
    "hour",
    "hour"
)
hour_features["time_value"] = hour_features["time_value"].astype(int)
hour_features = hour_features.sort_values(
    "time_value"
).reset_index(drop=True)
weekday_features = create_time_summary(
    df,
    "weekday_num",
    "weekday"
)
weekday_features["time_value"] = weekday_features[
    "time_value"
].map(weekday_map)
weekday_order = [
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday"
]
weekday_features["time_value"] = pd.Categorical(
    weekday_features["time_value"],
    categories=weekday_order,
    ordered=True
)
weekday_features = weekday_features.sort_values(
    "time_value"
).reset_index(drop=True)
day_type_features = create_time_summary(
    df,
    "day_type",
    "day_type"
)
day_type_order = [
    "Weekday",
    "Weekend"
]
day_type_features["time_value"] = pd.Categorical(
    day_type_features["time_value"],
    categories=day_type_order,
    ordered=True
)
day_type_features = day_type_features.sort_values(
    "time_value"
).reset_index(drop=True)
time_features = pd.concat(
    [
        hour_features,
        weekday_features,
        day_type_features
    ],
    ignore_index=True
)
time_features["time_value"] = (
    time_features["time_value"]
    .astype(str)
)
output_path = (
    "data/features/time_feature_hourly_weekly.csv"
)
time_features.to_csv(
    output_path,
    index=False
)
# peak_hour_features.csv
import pandas as pd
df = pd.read_parquet(
     "data/processed/user_behavior_clean.parquet"
)
df["time"] = pd.to_datetime(df["time"])
df["hour"] = df["time"].dt.hour
hourly = (
    df.groupby("hour")
    .agg(
        behavior_count=("behavior_name", "size"),
        pv_count=("behavior_name", lambda x: (x == "pv").sum()),
        fav_count=("behavior_name", lambda x: (x == "fav").sum()),
        cart_count=("behavior_name", lambda x: (x == "cart").sum()),
        buy_count=("behavior_name", lambda x: (x == "buy").sum())
    )
    .reset_index()
    .sort_values("hour")
)
p80 = hourly["behavior_count"].quantile(0.80)
hourly["hour_type"] = hourly["behavior_count"].apply(
    lambda x: "Peak" if x >= p80 else "Non-Peak"
)
peak_hours = hourly.loc[
    hourly["hour_type"] == "Peak", "hour"
].tolist()
non_peak_hours = hourly.loc[
    hourly["hour_type"] == "Non-Peak", "hour"
].tolist()
peak_summary = hourly[hourly["hour_type"] == "Peak"].sum(numeric_only=True)
non_peak_summary = hourly[hourly["hour_type"] == "Non-Peak"].sum(numeric_only=True)
result = pd.DataFrame([
    {
        "hour_type": "Peak",
        "hours": "|".join(map(str, peak_hours)),
        "behavior_count": int(peak_summary["behavior_count"]),
        "pv_count": int(peak_summary["pv_count"]),
        "fav_count": int(peak_summary["fav_count"]),
        "cart_count": int(peak_summary["cart_count"]),
        "buy_count": int(peak_summary["buy_count"])
    },
    {
        "hour_type": "Non-Peak",
        "hours": "|".join(map(str, non_peak_hours)),
        "behavior_count": int(non_peak_summary["behavior_count"]),
        "pv_count": int(non_peak_summary["pv_count"]),
        "fav_count": int(non_peak_summary["fav_count"]),
        "cart_count": int(non_peak_summary["cart_count"]),
        "buy_count": int(non_peak_summary["buy_count"])
    }
])
result.to_csv(
    "data/features/peak_hour_features.csv",
    index=False
)



# 4. 构建用户行为序列特征：
# 最近 N 次行为类型；
# 浏览到加购 / 收藏 / 购买的转移关系；
# 用户行为间隔；
# 用户是否存在连续行为链路。
# N=5
# 行为间隔 = 用户最近 5 次行为中，相邻行为之间的平均时间间隔。
# 浏览到加购 / 收藏 / 购买的转移关系定义：对每个用户的每个商品，按照行为发生时间 time 从早到晚排序，仅在相邻两条行为记录之间识别行为转移。转移必须发生在相同的 user_id 和相同的 item_id 内。
# 重点关注以下三种直接转移： 
#	PV → Favorite
#	PV → Cart
#	PV → Buy
# 用户是否存在连续行为链路定义：在同一 user_id、同一 item_id 内，按照 time 从早到晚排序，判断用户是否按照预定义的行为顺序完成连续的转化行为。若存在至少一条符合条件的行为链路，则记为 1，否则记为 0。
# 定义以下三类链路：
#	PV → Favorite → Buy 
#	PV → Cart → Buy 
#	PV → Favorite → Cart → Buy
# 产出：user_sequence_features.csv
import pandas as pd
df = pd.read_parquet(
     "data/processed/user_behavior_clean.parquet",
    columns=["user_id", "item_id", "time", "behavior_name"]
)
df["time"] = pd.to_datetime(df["time"])
df["behavior_name"] = df["behavior_name"].astype("string")
df_user = df.sort_values(
    ["user_id", "time"]
).copy()
recent_5_df = (
    df_user
    .groupby("user_id")
    .tail(5)
    .sort_values(["user_id", "time"])
)
recent_5 = (
    recent_5_df
    .groupby("user_id")["behavior_name"]
    .agg(lambda x: "|".join(x.astype(str)))
    .rename("recent_5_actions")
)
recent_5_df["interval_min"] = (
    recent_5_df
    .groupby("user_id")["time"]
    .diff()
    .dt.total_seconds()
    .div(60)
)
recent_5_interval = (
    recent_5_df
    .groupby("user_id")["interval_min"]
    .mean()
    .rename("avg_recent_5_interval_min")
)
item_df = df.sort_values(
    ["user_id", "item_id", "time"]
).copy()
item_group = item_df.groupby(
    ["user_id", "item_id"]
)
item_df["behavior_1"] = item_df["behavior_name"]
item_df["behavior_2"] = item_group["behavior_name"].shift(-1)
item_df["behavior_3"] = item_group["behavior_name"].shift(-2)
item_df["behavior_4"] = item_group["behavior_name"].shift(-3)
item_df["pv_to_fav"] = (
    (item_df["behavior_1"] == "pv") &
    (item_df["behavior_2"] == "fav")
).fillna(False).astype("int8")
item_df["pv_to_cart"] = (
    (item_df["behavior_1"] == "pv") &
    (item_df["behavior_2"] == "cart")
).fillna(False).astype("int8")
item_df["pv_to_buy"] = (
    (item_df["behavior_1"] == "pv") &
    (item_df["behavior_2"] == "buy")
).fillna(False).astype("int8")
transition_features = (
    item_df
    .groupby("user_id")[
        ["pv_to_fav", "pv_to_cart", "pv_to_buy"]
    ]
    .sum()
    .rename(columns={
        "pv_to_fav": "pv_to_fav_count",
        "pv_to_cart": "pv_to_cart_count",
        "pv_to_buy": "pv_to_buy_count"
    })
)
chain_1 = (
    (item_df["behavior_1"] == "pv") &
    (item_df["behavior_2"] == "fav") &
    (item_df["behavior_3"] == "buy")
)
chain_2 = (
    (item_df["behavior_1"] == "pv") &
    (item_df["behavior_2"] == "cart") &
    (item_df["behavior_3"] == "buy")
)
chain_3 = (
    (item_df["behavior_1"] == "pv") &
    (item_df["behavior_2"] == "fav") &
    (item_df["behavior_3"] == "cart") &
    (item_df["behavior_4"] == "buy")
)
item_df["behavior_chain"] = (
    chain_1 | chain_2 | chain_3
).fillna(False).astype("int8")
chain_features = (
    item_df
    .groupby("user_id")["behavior_chain"]
    .max()
    .rename("has_behavior_chain")
)
user_sequence_features = pd.concat(
    [
        recent_5,
        recent_5_interval,
        transition_features,
        chain_features
    ],
    axis=1
).reset_index()
user_sequence_features["avg_recent_5_interval_min"] = (
    user_sequence_features["avg_recent_5_interval_min"]
    .fillna(0)
    .round(2)
)
for col in [
    "pv_to_fav_count",
    "pv_to_cart_count",
    "pv_to_buy_count",
    "has_behavior_chain"
]:
    user_sequence_features[col] = (
        user_sequence_features[col]
        .fillna(0)
        .astype(int)
    )
output_path = (
   "data/features/user_sequence_features.csv"
)
user_sequence_features.to_csv(
    output_path,
    index=False
)
