import pandas as pd
import plotly.express as px
import streamlit as st


def show():

    st.header("阶段一基础 EDA")

    st.caption(
        "用户整体行为规模、购买结构与时间分布分析"
    )

    behavior = pd.read_csv(
        "data/interim/behavior_statistics.csv"
    )

    daily = pd.read_csv(
        "data/interim/daily_behavior.csv"
    )

    hourly = pd.read_csv(
        "data/interim/hourly_behavior.csv"
    )

    row = behavior.iloc[0]

    # =========================
    # 核心指标
    # =========================

    c1, c2, c3, c4 = st.columns(4)

    c1.metric(
        "总行为次数",
        f"{int(row['total_behavior_count']):,}"
    )

    c2.metric(
        "购买次数",
        f"{int(row['total_purchase_count']):,}"
    )

    c3.metric(
        "购买用户数",
        f"{int(row['purchase_users']):,}"
    )

    c4.metric(
        "复购用户数",
        f"{int(row['repeat_purchase_users']):,}"
    )

    st.divider()

    # =========================
    # 用户购买结构
    # =========================

    st.subheader("用户购买结构")

    user_structure = pd.DataFrame(
        {
            "用户类型": [
                "购买用户",
                "未购买用户",
                "复购用户"
            ],
            "用户数量": [
                int(row["purchase_users"]),
                int(row["non_purchase_users"]),
                int(row["repeat_purchase_users"])
            ]
        }
    )

    fig_user = px.bar(
        user_structure,
        x="用户类型",
        y="用户数量",
        text_auto=",",
        labels={
            "用户类型": "",
            "用户数量": "用户数"
        }
    )

    fig_user.update_layout(
        height=420,
        showlegend=False,
        dragmode=False
    )

    st.plotly_chart(
        fig_user,
        use_container_width=True,
        config={
            "scrollZoom": False,
            "displayModeBar": False
        }
    )

    st.caption(
        "注：复购用户属于购买用户的子集，因此不能与购买用户、未购买用户直接相加。"
    )

    st.divider()

    # =========================
    # 每日行为趋势
    # =========================

    st.subheader("每日行为趋势")

    daily["behavior_date"] = pd.to_datetime(
        daily["behavior_date"]
    )

    daily = daily.sort_values(
        "behavior_date"
    )

    fig_daily = px.line(
        daily,
        x="behavior_date",
        y="behavior_count",
        markers=True,
        labels={
            "behavior_date": "日期",
            "behavior_count": "行为次数"
        }
    )

    fig_daily.update_layout(
        height=450,
        xaxis_title="日期",
        yaxis_title="行为次数",
        dragmode=False
    )

    st.plotly_chart(
        fig_daily,
        use_container_width=True,
        config={
            "scrollZoom": False,
            "displayModeBar": False
        }
    )

    st.info(
        "分析结论：整体行为在 2025-12-12 出现明显峰值，"
        "说明该日期存在显著流量或活动效应，后续分析应关注特殊日期影响。"
    )

    st.divider()

    # =========================
    # 小时行为分布
    # =========================

    st.subheader("24 小时行为分布")

    hourly = hourly.sort_values(
        "behavior_hour"
    )

    fig_hourly = px.bar(
        hourly,
        x="behavior_hour",
        y="behavior_count",
        labels={
            "behavior_hour": "小时",
            "behavior_count": "行为次数"
        }
    )

    fig_hourly.update_layout(
        height=450,
        xaxis_title="小时",
        yaxis_title="行为次数",
        xaxis=dict(
            tickmode="linear",
            dtick=1
        ),
        dragmode=False
    )

    st.plotly_chart(
        fig_hourly,
        use_container_width=True,
        config={
            "scrollZoom": False,
            "displayModeBar": False
        }
    )

    st.info(
        "分析结论：用户行为主要集中在晚间，21:00 左右达到高峰，"
        "可作为用户触达和营销活动时间选择的重要参考。"
    )

    st.divider()

    # =========================
    # 时间特征摘要
    # =========================

    st.subheader("时间行为摘要")

    peak_day = daily.loc[
        daily["behavior_count"].idxmax()
    ]

    peak_hour = hourly.loc[
        hourly["behavior_count"].idxmax()
    ]

    c1, c2, c3 = st.columns(3)

    c1.metric(
        "分析天数",
        f"{len(daily)} 天"
    )

    c2.metric(
        "行为最高日期",
        peak_day["behavior_date"].strftime("%Y-%m-%d"),
        f"{int(peak_day['behavior_count']):,} 次"
    )

    c3.metric(
        "行为高峰小时",
        f"{int(peak_hour['behavior_hour']):02d}:00",
        f"{int(peak_hour['behavior_count']):,} 次"
    )
