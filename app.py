import streamlit as st
import re
from confluence import (
    get_all_pages,
    get_pages_by_ancestor,
    get_page_full,
    create_page,
    copy_page_ui_equivalent,
    apply_page_restrictions,
    update_page_title   # ⭐ 新增
)
from tree import build_page_tree, build_tree_for_select, build_id_map

# =========================
# 正则校验
# =========================
def validate_replacement(replacement: str):
    """
    只允许 Python 正则 replacement 语法：
    - \\1, \\g<1>
    禁止：
    - $1, $2
    """
    if re.search(r"\$\d+", replacement):
        raise ValueError(
            "❌ replacement 中检测到 '$1' 形式的分组引用，"
            "Python 正则不支持，请使用 \\1 或 \\g<1>"
        )

# =========================
# 页面配置
# =========================
st.set_page_config(
    page_title="Confluence 页面克隆工具（正则版）",
    layout="wide"
)

st.title("🎯 Confluence 页面克隆（正则标题强制生效版）")

if "tree_data" not in st.session_state:
    st.session_state.tree_data = []
    st.session_state.id_map = {}

# =========================
# Sidebar
# =========================
with st.sidebar:
    st.header("1️⃣ 认证")
    user_email = st.text_input("Confluence Email")
    user_token = st.text_input("API Token", type="password")

    st.header("2️⃣ 源空间")
    src_space = st.text_input("源空间 Key")
    src_root_id = st.text_input("源起始页面 ID（可选）")

    st.header("3️⃣ 目标空间")
    tar_space = st.text_input("目标空间 Key")
    target_parent_id = st.text_input("目标父页面 ID")

    st.header("4️⃣ 标题 / 内容正则替换（可选）")
    pattern = st.text_input(
        "正则 Pattern",
        placeholder="例如: (.*)-草稿"
    )
    replacement = st.text_input(
        "Replacement（使用 \\1 / \\g<1>）",
        placeholder="例如: \\1-正式"
    )

# =========================
# 核心同步函数
# =========================
def sync_page(source_page_id, current_target_parent):
    try:
        data = get_page_full(source_page_id, user_email, user_token)
        raw_title = data.get("title", "Untitled")
        body = data.get("body", {}).get("storage", {}).get("value", "")

        title = raw_title

        # ---------- 正则替换 ----------
        if pattern:
            validate_replacement(replacement)
            title = re.sub(pattern, replacement, title)
            body = re.sub(pattern, replacement, body)

        # ---------- 同空间复制 ----------
        if src_space == tar_space:
            st.write(f"📋 同空间复制：**{title}**")

            result = copy_page_ui_equivalent(
                source_page_id,
                current_target_parent,
                user_email,
                user_token
            )
            new_id = result.get("id")

            # ⭐ 强制修正标题（关键）
            if new_id and title != raw_title:
                update_page_title(
                    new_id,
                    title,
                    user_email,
                    user_token
                )

        # ---------- 跨空间创建 ----------
        else:
            st.write(f"📄 跨空间创建：**{title}**")
            result = create_page(
                tar_space,
                current_target_parent,
                title,
                body,
                user_email,
                user_token
            )
            new_id = result.get("id")

        # ---------- 权限同步 ----------
        if new_id:
            restrictions = data.get("restrictions")
            if restrictions:
                apply_page_restrictions(
                    new_id,
                    restrictions,
                    user_email,
                    user_token
                )

        return new_id

    except ValueError as ve:
        st.error(str(ve))
        st.stop()
    except Exception as e:
        st.error(f"同步页面失败 ({source_page_id}): {e}")
        return None

# =========================
# 递归处理
# =========================
def process_node_recursive(node_id, current_target_parent, checked_ids):
    node = st.session_state.id_map.get(node_id)
    if not node:
        return

    next_parent = current_target_parent

    if node_id in checked_ids:
        new_id = sync_page(node_id, current_target_parent)
        if new_id:
            next_parent = new_id

    for child in node.children:
        process_node_recursive(child.id, next_parent, checked_ids)

# =========================
# Step 1: 加载页面树
# =========================
if st.button("第一步：加载页面树"):
    if not all([user_email, user_token, src_space]):
        st.error("请填写认证信息和源空间")
    else:
        with st.spinner("加载中..."):
            if src_root_id.strip():
                pages = get_pages_by_ancestor(
                    src_space,
                    src_root_id,
                    user_email,
                    user_token
                )
            else:
                pages = get_all_pages(
                    src_space,
                    user_email,
                    user_token
                )

            roots = build_page_tree(pages)
            st.session_state.tree_data = [
                build_tree_for_select(r) for r in roots
            ]
            st.session_state.id_map = build_id_map(roots)

            st.success(f"成功加载 {len(pages)} 个页面")

# =========================
# Step 2: 选择并同步
# =========================
if st.session_state.tree_data:
    from streamlit_tree_select import tree_select

    st.divider()
    st.subheader("第二步：选择要同步的页面")

    selected = tree_select(
        st.session_state.tree_data,
        no_cascade=True,
        check_model="all"
    )

    checked_ids = set(selected.get("checked", []))

    if st.button("开始同步"):
        if not checked_ids:
            st.warning("请至少选择一个页面")
        elif not all([tar_space, target_parent_id]):
            st.error("请填写目标空间和父页面 ID")
        else:
            with st.status("同步中...", expanded=True):
                for r in st.session_state.tree_data:
                    process_node_recursive(
                        r["value"],
                        target_parent_id,
                        checked_ids
                    )
            st.success("✅ 同步完成")
