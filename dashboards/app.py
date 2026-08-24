import importlib

import streamlit as st


st.set_page_config(
    page_title="淘宝用户行为分析看板",
    layout="wide",
)


if "page" not in st.session_state:
    st.session_state.page = "home"


# =========================
# Sidebar navigation
# =========================

with st.sidebar:

    st.title("导航")

    pages = [
        ("首页", "home"),
        ("基础 EDA", "eda"),
        ("用户分析", "user"),
        ("商品分析", "item"),
        ("类目分析", "category"),
        ("转化分析", "conversion"),
    ]

    for label, page_name in pages:

        button_type = (
            "primary"
            if st.session_state.page == page_name
            else "secondary"
        )

        if st.button(
            label,
            use_container_width=True,
            key=f"nav_{page_name}",
            type=button_type,
        ):
            st.session_state.page = page_name
            st.rerun()

    st.divider()

    st.caption(
        "阶段一 EDA + 阶段二特征分析"
    )


# =========================
# Main title
# =========================

st.title("淘宝用户行为分析看板")

st.caption(
    "商品、类目与用户行为转化分析"
)

st.divider()


# =========================
# Page routing
# =========================

if st.session_state.page == "home":
    import views.home as page

elif st.session_state.page == "eda":
    import views.eda as page

elif st.session_state.page == "user":
    import views.user as page

elif st.session_state.page == "item":
    import views.item as page

elif st.session_state.page == "category":
    import views.category as page

elif st.session_state.page == "conversion":
    import views.conversion as page

else:
    st.session_state.page = "home"
    import views.home as page


importlib.reload(page)
page.show()
