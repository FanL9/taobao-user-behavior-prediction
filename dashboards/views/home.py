import streamlit as st
import pyarrow.parquet as pq


def show():

    st.header("数据总览")

    st.caption(
        "淘宝用户行为整体表现与转化情况"
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


    c1,c2,c3,c4 = st.columns(4)


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
        f"{user.user_is_buyer.sum():,}"
    )


    st.divider()


    left,right = st.columns(2)


    with left:

        st.subheader(
            "行为转化漏斗"
        )

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

        st.subheader(
            "转化率"
        )

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


    st.subheader(
        "核心指标"
    )


    col1,col2 = st.columns(2)


    with col1:

        top_item = (
            item.sort_values(
                "item_buy_count",
                ascending=False
            )
            .head(5)
            [
                [
                    "item_id",
                    "item_buy_count"
                ]
            ]
        )

        st.write(
            "热门商品 Top5"
        )

        st.dataframe(
            top_item,
            use_container_width=True
        )


    with col2:

        top_category = (
            category.sort_values(
                "category_buy_count",
                ascending=False
            )
            .head(5)
            [
                [
                    "category_id",
                    "category_buy_count"
                ]
            ]
        )

        st.write(
            "热门类目 Top5"
        )

        st.dataframe(
            top_category,
            use_container_width=True
        )
