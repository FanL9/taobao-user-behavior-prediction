import subprocess, sys; subprocess.check_call([sys.executable, "-m", "pip", "install", "pyarrow"])

# 基础EDA
# 1
# 统计四类行为分布：
# 浏览 `pv`；
# 收藏 `fav`；
# 加购 `cart`；
# 购买 `buy`。
# behavior_distribution.csv	
import pandas as pd
df = pd.read_parquet(
    "taobao-user-behavior-prediction/data/processed/user_behavior_clean.parquet",
    columns=["behavior_name"]
)
df = df[df["behavior_name"].isin(["pv", "fav", "cart", "buy"])]
result = (
    df.groupby("behavior_name")
      .size()
      .reset_index(name="behavior_count")
)
total_count = result["behavior_count"].sum()
result["percentage"] = (
    result["behavior_count"] / total_count * 100
).round(2)
result = result.sort_values(
    "behavior_count",
    ascending=False
).reset_index(drop=True)
print(result)
result.to_csv(
    "taobao-user-behavior-prediction/data/interim/behavior_distribution.csv",
    index=False
)



# 2
# 用户行为次数；
# 用户购买次数；
# 购买用户数；
# 未购买用户数；
# 复购用户数。
# 购买用户：只要有≥1 条 buy 行为就算；
# 未购买用户：有浏览 / 收藏 / 加购行为，但完全没有 buy 记录；
# 复购用户：同一个 user_id，购买行为≥2 次（按行为记录，不是按订单）。
# behavior_statistics.csv
import pandas as pd
df = pd.read_parquet(
    "taobao-user-behavior-prediction/data/processed/user_behavior_clean.parquet",
    columns=["user_id", "behavior_name"]
)
total_behavior_count = len(df)
buy_df = df[df["behavior_name"] == "buy"]
total_purchase_count = len(buy_df)
purchase_users = buy_df["user_id"].nunique()
total_users = df["user_id"].nunique()
non_purchase_users = total_users - purchase_users
buy_counts = buy_df.groupby("user_id").size()
repeat_purchase_users = (buy_counts >= 2).sum()
result = pd.DataFrame({
    "total_behavior_count": [total_behavior_count],
    "total_purchase_count": [total_purchase_count],
    "purchase_users": [purchase_users],
    "non_purchase_users": [non_purchase_users],
    "repeat_purchase_users": [repeat_purchase_users]
})
print(result)
result.to_csv(
    "taobao-user-behavior-prediction/data/interim/behavior_statistics.csv",
    index=False
)



# 3
# 统计商品行为：
# 商品浏览次数；
# 商品收藏次数；
# 商品加购次数；
# 商品购买次数；
# 热门商品。
# item_statistics.csv
import pandas as pd
df = pd.read_parquet(
    "taobao-user-behavior-prediction/data/processed/user_behavior_clean.parquet",
    columns=["item_id", "behavior_type"]
)
result = (
    df.groupby("item_id")["behavior_type"]
      .value_counts()
      .unstack(fill_value=0)
      .reindex(columns=[1, 2, 3, 4], fill_value=0)
      .reset_index()
)
result.columns = [
    "item_id",
    "pv_count",
    "fav_count",
    "cart_count",
    "buy_count"
]
result.to_csv(
    "taobao-user-behavior-prediction/data/interim/item_statistics.csv",
    index=False
)
# 热门商品 = 按购买次数 buy_count 排名前 10 的商品。
# top_10_item.csv
import pandas as pd
df = pd.read_csv(
    "taobao-user-behavior-prediction/data/processed/item_statistics.csv"
)
result = (
    df.sort_values("buy_count", ascending=False)
      .head(10)
      .reset_index(drop=True)
)
result.to_csv(
    "taobao-user-behavior-prediction/data/interim/top_10_item.csv",
    index=False
)



# 4
# 统计类目行为：
# 类目行为总量；
# 类目购买量；
# 热门类目；
# 类目购买占比。
# category_statistics.csv
import pandas as pd
df = pd.read_parquet(
    "taobao-user-behavior-prediction/data/processed/user_behavior_clean.parquet",
    columns=["category_id", "behavior_type"]
)
result = (
    df.groupby("category_id")
      .agg(
          total_behavior_count=("behavior_type", "size"),
          buy_count=("behavior_type", lambda x: (x == 4).sum())
      )
      .reset_index()
)
total_buy_count = result["buy_count"].sum()
result["buy_percentage"] = (
    result["buy_count"] / total_buy_count * 100
).round(2)
result = result.sort_values(
    "buy_count",
    ascending=False
).reset_index(drop=True)
result.to_csv(
    "taobao-user-behavior-prediction/data/interim/category_statistics.csv",
    index=False
)
# 热门类目= 按购买次数 buy_count 排名前 10 的类目。
# top_10_category.csv
import pandas as pd
df = pd.read_csv(
    "taobao-user-behavior-prediction/data/processed/category_statistics.csv"
)
result = (
    df.sort_values(
        ["buy_count", "category_id"],
        ascending=[False, True]
    )
    .head(10)
    .reset_index(drop=True)
)
result.to_csv(
    "taobao-user-behavior-prediction/data/interim/top_10_category.csv",
    index=False
)



# 5
# 统计时间分布：
# 日期维度行为量；
# 小时维度行为量；
# 不同行为类型的时间分布。
df = pd.read_parquet(
    "taobao-user-behavior-prediction/data/processed/user_behavior_clean.parquet",
    columns=["behavior_date", "behavior_hour", "behavior_name"]
)
# daily_behavior.csv
daily_result = (
    df.groupby("behavior_date")
      .size()
      .reset_index(name="behavior_count")
      .sort_values("behavior_date")
      .reset_index(drop=True)
)
daily_result.to_csv(
    "taobao-user-behavior-prediction/data/interim/daily_behavior.csv",
    index=False
)
# hourly_behavior.csv
hourly_result = (
    df.groupby("behavior_hour")
      .size()
      .reset_index(name="behavior_count")
      .sort_values("behavior_hour")
      .reset_index(drop=True)
)
hourly_result.to_csv(
    "taobao-user-behavior-prediction/data/interim/hourly_behavior.csv",
    index=False
)
# behavior_hourly_distribution.csv
hourly_distribution = (
    df.groupby(["behavior_hour", "behavior_name"])
      .size()
      .unstack(fill_value=0)
      .reindex(columns=["pv", "fav", "cart", "buy"], fill_value=0)
      .reset_index()
)
hourly_distribution.columns = [
    "behavior_hour",
    "pv_count",
    "fav_count",
    "cart_count",
    "buy_count"
]
hourly_distribution = hourly_distribution.sort_values(
    "behavior_hour"
).reset_index(drop=True)
hourly_distribution.to_csv(
    "taobao-user-behavior-prediction/data/interim/behavior_hourly_distribution.csv",
    index=False
)



# 6
# 构建初步转化漏斗：
# 浏览；
# 收藏；
# 加购；
# 购买。
# descriptive_funnel.csv
import pandas as pd
df = pd.read_parquet(
    "taobao-user-behavior-prediction/data/processed/user_behavior_clean.parquet",
    columns=["behavior_type"]
)
behavior_counts = df["behavior_type"].value_counts()
pv_count = behavior_counts.get(1, 0)
fav_count = behavior_counts.get(2, 0)
cart_count = behavior_counts.get(3, 0)
buy_count = behavior_counts.get(4, 0)
result = pd.DataFrame({
    "stage": ["PV", "Favorite", "Cart", "Purchase"],
    "behavior_count": [
        pv_count,
        fav_count,
        cart_count,
        buy_count
    ],
    "relative_to_pv": [
        100.00,
        round(fav_count * 100.0 / pv_count, 2),
        round(cart_count * 100.0 / pv_count, 2),
        round(buy_count * 100.0 / pv_count, 2)
    ]
})
result.to_csv(
    "taobao-user-behavior-prediction/data/interim/descriptive_funnel.csv",
    index=False
)

