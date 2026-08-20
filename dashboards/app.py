import importlib

import streamlit as st


st.set_page_config(
    page_title="淘宝用户行为分析看板",
    layout="wide",
)


if "page" not in st.session_state:
    st.session_state.page = "home"


st.title("淘宝用户行为分析看板")

st.caption("商品、类目与用户行为转化分析")


st.write("")


cols = st.columns(4)

pages = [
    ("首页", "home"),
    ("商品分析", "item"),
    ("类目分析", "category"),
    ("转化分析", "conversion"),
]


for col, (label, page_name) in zip(cols, pages):
    with col:
        if st.button(
            label,
            use_container_width=True,
            key=f"nav_{page_name}",
        ):
            st.session_state.page = page_name
            st.rerun()


st.divider()


if st.session_state.page == "home":
    import views.home as page

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



