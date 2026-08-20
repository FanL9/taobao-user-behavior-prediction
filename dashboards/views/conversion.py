import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import pyarrow.parquet as pq
import streamlit as st


def show():

    st.header("转化分析")

    st.caption(
        "浏览、收藏、加购与购买行为的整体转化表现"
    )

    df = pq.read_table(
        "data/features/dashboard/conversion_funnel.parquet"
    ).to_pandas()

    row = df.iloc[0]

    c1, c2, c3, c4 = st.columns(4)

    c1.metric(
        "浏览次数",
        f"{int(row['pv_count']):,}"
    )

    c2.metric(
        "收藏次数",
        f"{int(row['fav_count']):,}"
    )

    c3.metric(
        "加购次数",
        f"{int(row['cart_count']):,}"
    )

    c4.metric(
        "购买次数",
        f"{int(row['buy_count']):,}"
    )

    st.divider()

    st.subheader("行为转化漏斗")

    funnel = go.Figure(
        go.Funnel(
            y=[
                "浏览",
                "加购",
                "购买"
            ],
            x=[
                int(row["pv_count"]),
                int(row["cart_count"]),
                int(row["buy_count"])
            ],
            textinfo="value+percent initial",
            hovertemplate=(
                "%{y}<br>"
                "行为次数：%{value:,}<br>"
                "相对浏览：%{percentInitial:.2%}"
                "<extra></extra>"
            )
        )
    )

    funnel.update_layout(
        height=520,
        margin=dict(
            l=80,
            r=80,
            t=30,
            b=30
        ),
        dragmode=False
    )

    st.plotly_chart(
        funnel,
        use_container_width=True,
        config={
            "scrollZoom": False,
            "displayModeBar": False,
            "doubleClick": False
        }
    )

    st.divider()

    st.subheader("关键转化率")

    rate_df = pd.DataFrame(
        {
            "转化路径": [
                "浏览 → 收藏",
                "浏览 → 加购",
                "浏览 → 购买",
                "收藏 → 购买",
                "加购 → 购买"
            ],
            "转化率": [
                row["pv_to_fav_rate"],
                row["pv_to_cart_rate"],
                row["pv_to_buy_rate"],
                row["fav_to_buy_rate"],
                row["cart_to_buy_rate"]
            ]
        }
    )

    fig_rate = px.bar(
        rate_df,
        x="转化路径",
        y="转化率",
        text_auto=".2%"
    )

    fig_rate.update_layout(
        height=430,
        xaxis_title="",
        yaxis_title="转化率",
        yaxis_tickformat=".1%",
        dragmode=False
    )

    st.plotly_chart(
        fig_rate,
        use_container_width=True,
        config={
            "scrollZoom": False,
            "displayModeBar": False
        }
    )

    st.caption(
        "注：当前转化率按行为次数计算，用于描述整体行为结构，不等同于用户级路径转化率。"
    )

