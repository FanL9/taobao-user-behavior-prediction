import streamlit as st
import pyarrow.parquet as pq
import plotly.express as px


def show():

    st.header("商品分析")

    st.caption(
        "商品热度、流量与购买转化表现"
    )

    df = pq.read_table(
        "data/features/dashboard/item_conversion_analysis.parquet"
    ).to_pandas()

    c1, c2, c3 = st.columns(3)

    c1.metric(
        "商品数量",
        f"{len(df):,}"
    )

    c2.metric(
        "行为总量",
        f"{df['item_total_count'].sum():,}"
    )

    c3.metric(
        "购买次数",
        f"{df['item_buy_count'].sum():,}"
    )

    st.divider()

    st.subheader("热门商品 Top20")

    top = (
        df.sort_values(
            "item_buy_count",
            ascending=False
        )
        .head(20)
        .copy()
    )

    top["item_id"] = top["item_id"].astype(str)

    fig_top = px.bar(
        top,
        x="item_id",
        y="item_buy_count",
        labels={
            "item_id": "商品 ID",
            "item_buy_count": "购买次数"
        }
    )

    fig_top.update_layout(
        xaxis_title="商品 ID",
        yaxis_title="购买次数",
        showlegend=False
    )

    st.plotly_chart(
        fig_top,
        use_container_width=True
    )

    st.divider()

    st.subheader("商品热度与转化率")

    scatter_df = df[
        (df["item_pv_count"] > 0)
        & (df["item_total_count"] > 0)
    ].copy()

    # 避免极端低流量商品把转化率图拉坏
    scatter_df = scatter_df[
        scatter_df["item_pv_count"] >= 5
    ]

    # 大量商品全部绘制会比较卡，只取热度较高的一部分展示
    scatter_df = scatter_df.nlargest(
        5000,
        "item_total_count"
    )

    fig_scatter = px.scatter(
        scatter_df,
        x="item_total_count",
        y="item_buy_to_pv_rate",
        size="item_buy_count",
        hover_data=[
            "item_id",
            "item_pv_count",
            "item_buy_count"
        ],
        labels={
            "item_total_count": "商品行为总量",
            "item_buy_to_pv_rate": "购买 / 浏览转化率",
            "item_buy_count": "购买次数"
        }
    )

    fig_scatter.update_layout(
        xaxis_title="商品热度（行为总量）",
        yaxis_title="购买转化率"
    )

    st.plotly_chart(
        fig_scatter,
        use_container_width=True
    )

    st.divider()

    st.subheader("热门商品明细")

    display_df = top[
        [
            "item_id",
            "item_total_count",
            "item_pv_count",
            "item_buy_count",
            "item_buy_to_pv_rate"
        ]
    ].copy()

    display_df.columns = [
        "商品 ID",
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

