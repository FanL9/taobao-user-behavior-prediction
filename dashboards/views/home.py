import streamlit as st
import pyarrow.parquet as pq


def show():

    st.header("数据总览")

    st.caption(
        "阶段一基础 EDA 与阶段二特征分析核心结果"
    )

    user = pq.read_table(
        "data/features/user_features.parquet"
    ).to_pandas()

    item = pq.read_table(
        "data/features/item_features.parquet"
    ).to_pandas()

    category = pq.read_table(
        "data/features/category_features.parquet"
    ).to_pandas()

    conversion = pq.read_table(
        "data/features/conversion_features.parquet"
    ).to_pandas()

    row = conversion.iloc[0]

    # =========================
    # 核心指标
    # =========================

    c1, c2, c3, c4 = st.columns(4)

    c1.metric(
        "用户数量",
        f"{len(user):,}"
    )

    c2.metric(
        "商品数量",
        f"{len(item):,}"
    )

    c3.metric(
        "类目数量",
        f"{len(category):,}"
    )

    c4.metric(
        "购买用户",
        f"{int(user['user_is_buyer'].sum()):,}"
    )

    st.divider()

    # =========================
    # 原首页图表
    # =========================

    left, right = st.columns(2)

    with left:

        st.subheader("行为转化漏斗")

        funnel = conversion.iloc[0][
            [
                "pv_count",
                "fav_count",
                "cart_count",
                "buy_count"
            ]
        ]

        st.bar_chart(funnel)

    with right:

        st.subheader("转化率")

        rate = conversion.iloc[0][
            [
                "pv_to_fav_rate",
                "pv_to_cart_rate",
                "pv_to_buy_rate",
                "cart_to_buy_rate"
            ]
        ]

        st.bar_chart(rate)

    st.divider()

    # =========================
    # 阶段一结论
    # =========================

    st.subheader("阶段一 EDA 核心结论")

    left, right = st.columns(2)

    with left:
        st.info(
            "时间趋势：整体用户行为在 2025-12-12 出现明显峰值，"
            "说明该日期存在显著流量或活动效应。"
        )

    with right:
        st.info(
            "活跃时段：用户行为主要集中在晚间，21:00 左右达到高峰，"
            "可作为营销触达时间选择的重要参考。"
        )

    st.divider()

    # =========================
    # 阶段二结论
    # =========================

    st.subheader("阶段二特征分析核心结论")

    c1, c2 = st.columns(2)

    with c1:
        st.success(
            "用户活跃度：高活跃用户购买比例明显高于低活跃用户，"
            "活跃度对购买倾向具有明显区分能力。"
        )

        st.success(
            "行为深度：随着用户行为深度提升，购买用户比例持续提高，"
            "行为总量是重要购买预测特征。"
        )

    with c2:
        st.success(
            "商品与类目：商品热度、类目流量与购买转化表现存在明显差异，"
            "适合用于商品和类目分层。"
        )

        st.success(
            "转化链路：加购规模明显高于最终购买规模，"
            "加购未购买用户是后续重点召回人群。"
        )

    st.divider()

    # =========================
    # 热门商品 / 类目
    # =========================

    left, right = st.columns(2)

    with left:

        st.subheader("热门商品 Top5")

        top_item = (
            item.sort_values(
                "item_buy_count",
                ascending=False
            )
            .head(5)[
                [
                    "item_id",
                    "item_buy_count"
                ]
            ]
            .copy()
        )

        top_item.columns = [
            "商品 ID",
            "购买次数"
        ]

        st.dataframe(
            top_item,
            use_container_width=True,
            hide_index=True
        )

    with right:

        st.subheader("热门类目 Top5")

        top_category = (
            category.sort_values(
                "category_buy_count",
                ascending=False
            )
            .head(5)[
                [
                    "category_id",
                    "category_buy_count"
                ]
            ]
            .copy()
        )

        top_category.columns = [
            "类目 ID",
            "购买次数"
        ]

        st.dataframe(
            top_category,
            use_container_width=True,
            hide_index=True
        )

    st.caption(
        "详细分析请通过顶部导航进入基础 EDA、用户分析、商品分析、类目分析和转化分析页面。"
    )
