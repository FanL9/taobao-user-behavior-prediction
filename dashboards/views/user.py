import numpy as np
import pandas as pd
import plotly.express as px
import pyarrow.parquet as pq
import streamlit as st


def show():

    st.header("用户分析")

    st.caption(
        "阶段二用户活跃度、行为深度与购买转化特征分析"
    )

    df = pq.read_table(
        "data/features/user_features.parquet"
    ).to_pandas()

    # =========================
    # 核心指标
    # =========================

    c1, c2, c3, c4 = st.columns(4)

    c1.metric(
        "用户数量",
        f"{len(df):,}"
    )

    c2.metric(
        "购买用户",
        f"{int(df['user_is_buyer'].sum()):,}"
    )

    c3.metric(
        "复购用户",
        f"{int(df['user_is_repeat_buyer'].sum()):,}"
    )

    c4.metric(
        "平均活跃天数",
        f"{df['user_active_day_count'].mean():.1f} 天"
    )

    st.divider()

    # =========================
    # 用户活跃度
    # =========================

    st.subheader("用户活跃度与购买率")

    activity = (
        df.groupby(
            "user_activity_level",
            as_index=False
        )
        .agg(
            用户数量=("user_id", "count"),
            购买用户数=("user_is_buyer", "sum"),
            平均购买次数=("user_buy_count", "mean"),
            平均活跃天数=("user_active_day_count", "mean")
        )
    )

    activity["购买用户比例"] = (
        activity["购买用户数"]
        / activity["用户数量"]
    )

    left, right = st.columns(2)

    with left:

        fig_activity_count = px.bar(
            activity,
            x="user_activity_level",
            y="用户数量",
            text_auto=",",
            labels={
                "user_activity_level": "用户活跃层级",
                "用户数量": "用户数量"
            }
        )

        fig_activity_count.update_layout(
            title="不同活跃层级用户数量",
            xaxis_title="用户活跃层级",
            yaxis_title="用户数量",
            showlegend=False,
            dragmode=False
        )

        st.plotly_chart(
            fig_activity_count,
            use_container_width=True,
            config={
                "scrollZoom": False,
                "displayModeBar": False
            }
        )

    with right:

        fig_activity_rate = px.bar(
            activity,
            x="user_activity_level",
            y="购买用户比例",
            text_auto=".2%",
            labels={
                "user_activity_level": "用户活跃层级",
                "购买用户比例": "购买用户比例"
            }
        )

        fig_activity_rate.update_layout(
            title="不同活跃层级购买用户比例",
            xaxis_title="用户活跃层级",
            yaxis_title="购买用户比例",
            yaxis_tickformat=".1%",
            showlegend=False,
            dragmode=False
        )

        st.plotly_chart(
            fig_activity_rate,
            use_container_width=True,
            config={
                "scrollZoom": False,
                "displayModeBar": False
            }
        )

    st.dataframe(
        activity,
        use_container_width=True,
        hide_index=True
    )

    st.info(
        "分析结论：高活跃用户的购买用户比例明显高于低活跃用户，"
        "说明用户活跃度与购买倾向存在较强正向关系。"
    )

    st.divider()

    # =========================
    # 活跃天数与购买
    # =========================

    st.subheader("活跃天数与购买行为")

    scatter_activity = df[
        [
            "user_id",
            "user_active_day_count",
            "user_avg_daily_behavior_count",
            "user_total_count",
            "user_buy_count",
            "user_is_buyer"
        ]
    ].copy()

    fig_active_days = px.scatter(
        scatter_activity,
        x="user_active_day_count",
        y="user_buy_count",
        size="user_total_count",
        color="user_is_buyer",
        hover_data=[
            "user_id",
            "user_avg_daily_behavior_count"
        ],
        labels={
            "user_active_day_count": "活跃天数",
            "user_buy_count": "购买次数",
            "user_total_count": "行为总量",
            "user_is_buyer": "是否购买"
        }
    )

    fig_active_days.update_layout(
        height=480,
        xaxis_title="用户活跃天数",
        yaxis_title="购买次数",
        dragmode=False
    )

    st.plotly_chart(
        fig_active_days,
        use_container_width=True,
        config={
            "scrollZoom": False,
            "displayModeBar": False
        }
    )

    st.divider()

    # =========================
    # 用户行为深度
    # =========================

    st.subheader("用户行为深度与购买率")

    depth_df = df.copy()

    # 使用行为总量的分位数进行分层，
    # 避免极端高活跃用户导致区间严重失衡。
    depth_df["behavior_depth"] = pd.qcut(
        depth_df["user_total_count"],
        q=4,
        labels=[
            "低行为深度",
            "中低行为深度",
            "中高行为深度",
            "高行为深度"
        ],
        duplicates="drop"
    )

    depth = (
        depth_df.groupby(
            "behavior_depth",
            observed=True,
            as_index=False
        )
        .agg(
            用户数量=("user_id", "count"),
            购买用户数=("user_is_buyer", "sum"),
            平均行为次数=("user_total_count", "mean"),
            平均交互商品数=("user_unique_item_count", "mean"),
            平均购买次数=("user_buy_count", "mean")
        )
    )

    depth["购买用户比例"] = (
        depth["购买用户数"]
        / depth["用户数量"]
    )

    left, right = st.columns(2)

    with left:

        fig_depth_count = px.bar(
            depth,
            x="behavior_depth",
            y="用户数量",
            text_auto=",",
            labels={
                "behavior_depth": "行为深度",
                "用户数量": "用户数量"
            }
        )

        fig_depth_count.update_layout(
            title="不同用户行为深度分布",
            xaxis_title="行为深度",
            yaxis_title="用户数量",
            showlegend=False,
            dragmode=False
        )

        st.plotly_chart(
            fig_depth_count,
            use_container_width=True,
            config={
                "scrollZoom": False,
                "displayModeBar": False
            }
        )

    with right:

        fig_depth_rate = px.bar(
            depth,
            x="behavior_depth",
            y="购买用户比例",
            text_auto=".2%",
            labels={
                "behavior_depth": "行为深度",
                "购买用户比例": "购买用户比例"
            }
        )

        fig_depth_rate.update_layout(
            title="行为深度与购买用户比例",
            xaxis_title="行为深度",
            yaxis_title="购买用户比例",
            yaxis_tickformat=".1%",
            showlegend=False,
            dragmode=False
        )

        st.plotly_chart(
            fig_depth_rate,
            use_container_width=True,
            config={
                "scrollZoom": False,
                "displayModeBar": False
            }
        )

    st.dataframe(
        depth,
        use_container_width=True,
        hide_index=True
    )

    st.info(
        "分析结论：随着用户行为深度提升，购买用户比例明显上升。"
        "高行为深度用户具有更强的购买倾向，行为总量可作为重要购买预测特征。"
    )

    st.divider()

    # =========================
    # 交互商品广度
    # =========================

    st.subheader("交互商品广度与购买行为")

    plot_df = df[
        [
            "user_id",
            "user_unique_item_count",
            "user_unique_category_count",
            "user_buy_count",
            "user_total_count"
        ]
    ].copy()

    fig_items = px.scatter(
        plot_df,
        x="user_unique_item_count",
        y="user_buy_count",
        size="user_total_count",
        hover_data=[
            "user_id",
            "user_unique_category_count"
        ],
        labels={
            "user_unique_item_count": "交互商品数量",
            "user_buy_count": "购买次数",
            "user_total_count": "行为总量",
            "user_unique_category_count": "交互类目数量"
        }
    )

    fig_items.update_layout(
        height=480,
        xaxis_title="交互商品数量",
        yaxis_title="购买次数",
        dragmode=False
    )

    st.plotly_chart(
        fig_items,
        use_container_width=True,
        config={
            "scrollZoom": False,
            "displayModeBar": False
        }
    )

    st.info(
        "分析结论：用户交互商品数量增加时，购买次数整体呈上升趋势，"
        "说明更广的商品探索行为通常伴随更高的购买活跃度。"
    )

    st.divider()

    # =========================
    # 收藏 / 加购 / 购买
    # =========================

    st.subheader("收藏、加购与购买关系")

    interaction = pd.DataFrame(
        {
            "行为": [
                "收藏",
                "加购",
                "购买"
            ],
            "行为次数": [
                int(df["user_fav_count"].sum()),
                int(df["user_cart_count"].sum()),
                int(df["user_buy_count"].sum())
            ]
        }
    )

    fig_interaction = px.bar(
        interaction,
        x="行为",
        y="行为次数",
        text_auto=","
    )

    fig_interaction.update_layout(
        height=420,
        xaxis_title="",
        yaxis_title="行为次数",
        showlegend=False,
        dragmode=False
    )

    st.plotly_chart(
        fig_interaction,
        use_container_width=True,
        config={
            "scrollZoom": False,
            "displayModeBar": False
        }
    )


    st.info(
        "分析结论：加购行为规模明显高于最终购买行为，"
        "说明存在较大的加购未购买用户群体，可作为后续召回和转化运营的重点对象。"
    )
