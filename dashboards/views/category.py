import numpy as np
import plotly.express as px
import pyarrow.parquet as pq
import streamlit as st


def show():

    st.header("类目分析")

    st.caption(
        "类目流量规模、购买表现与长尾结构分析"
    )

    df = pq.read_table(
        "data/features/dashboard/category_conversion_analysis.parquet"
    ).to_pandas()

    c1, c2, c3 = st.columns(3)

    c1.metric(
        "类目数量",
        f"{len(df):,}"
    )

    c2.metric(
        "行为总量",
        f"{int(df['category_total_count'].sum()):,}"
    )

    c3.metric(
        "购买次数",
        f"{int(df['category_buy_count'].sum()):,}"
    )

    st.divider()

    st.subheader("热门类目 Top20")

    top = (
        df.sort_values(
            "category_buy_count",
            ascending=False
        )
        .head(20)
        .copy()
    )

    top["category_id"] = top["category_id"].astype(str)

    fig_top = px.bar(
        top,
        x="category_id",
        y="category_buy_count",
        labels={
            "category_id": "类目 ID",
            "category_buy_count": "购买次数"
        }
    )

    fig_top.update_layout(
        xaxis_title="类目 ID",
        yaxis_title="购买次数",
        showlegend=False,
        dragmode=False
    )

    st.plotly_chart(
        fig_top,
        use_container_width=True,
        config={
            "scrollZoom": False,
            "displayModeBar": False
        }
    )

    st.divider()

    st.subheader("类目流量与转化率")

    scatter_df = df[
        (df["category_pv_count"] > 0)
        & (df["category_total_count"] > 0)
    ].copy()

    scatter_df = scatter_df.nlargest(
        3000,
        "category_total_count"
    )

    fig_scatter = px.scatter(
        scatter_df,
        x="category_total_count",
        y="category_buy_to_pv_rate",
        size="category_buy_count",
        hover_data=[
            "category_id",
            "category_pv_count",
            "category_buy_count"
        ],
        labels={
            "category_total_count": "类目行为总量",
            "category_buy_to_pv_rate": "购买 / 浏览转化率",
            "category_buy_count": "购买次数"
        }
    )

    fig_scatter.update_layout(
        xaxis_title="类目流量（行为总量）",
        yaxis_title="购买转化率",
        dragmode=False
    )

    st.plotly_chart(
        fig_scatter,
        use_container_width=True,
        config={
            "scrollZoom": False,
            "displayModeBar": False
        }
    )

    st.divider()

    st.subheader("热门与长尾类目")

    traffic_q80 = df["category_total_count"].quantile(0.80)
    traffic_q20 = df["category_total_count"].quantile(0.20)

    segmented = df.copy()

    segmented["category_segment"] = np.select(
        [
            segmented["category_total_count"] >= traffic_q80,
            segmented["category_total_count"] <= traffic_q20
        ],
        [
            "热门类目",
            "长尾类目"
        ],
        default="普通类目"
    )

    segment_summary = (
        segmented.groupby(
            "category_segment",
            as_index=False
        )
        .agg(
            类目数量=("category_id", "count"),
            行为总量=("category_total_count", "sum"),
            购买次数=("category_buy_count", "sum"),
            平均购买转化率=("category_buy_to_pv_rate", "mean")
        )
    )

    segment_order = {
        "热门类目": 0,
        "普通类目": 1,
        "长尾类目": 2
    }

    segment_summary["_order"] = (
        segment_summary["category_segment"]
        .map(segment_order)
    )

    segment_summary = (
        segment_summary
        .sort_values("_order")
        .drop(columns="_order")
    )

    st.dataframe(
        segment_summary,
        use_container_width=True,
        hide_index=True
    )

    st.divider()

    st.subheader("热门类目明细")

    display_df = top[
        [
            "category_id",
            "category_total_count",
            "category_pv_count",
            "category_buy_count",
            "category_buy_to_pv_rate"
        ]
    ].copy()

    display_df.columns = [
        "类目 ID",
        "行为总量",
        "浏览次数",
        "购买次数",
        "购买转化率"
    ]

    st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True
    )

