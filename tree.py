# tree.py

class PageNode:
    def __init__(self, page):
        self.id = str(page.get("id"))
        self.title = page.get("title", "无标题页面")
        self.children = []
        # 获取父节点 ID 以便后续判断根节点
        ancestors = page.get("ancestors", [])
        self.parent_id = str(ancestors[-1].get("id")) if ancestors else None

def build_page_tree(pages):
    """构建页面树结构"""
    id_map = {str(p["id"]): PageNode(p) for p in pages if "id" in p}
    child_ids = set()

    for p in pages:
        pid = str(p["id"])
        node = id_map.get(pid)
        if node and node.parent_id in id_map:
            id_map[node.parent_id].children.append(node)
            child_ids.add(pid)
    
    # 返回所有根节点（即父节点不在当前列表中的节点）
    roots = [node for pid, node in id_map.items() if pid not in child_ids]
    return roots

def build_tree_for_select(node: PageNode):
    """转换为 tree_select 要求的字典格式"""
    return {
        "value": node.id,
        "label": node.title,
        "children": [build_tree_for_select(c) for c in node.children]
    }

def build_id_map(roots):
    """构建全局 ID 到 PageNode 对象的映射"""
    mapping = {}
    def dfs(node):
        mapping[node.id] = node
        for c in node.children:
            dfs(c)
    for r in roots:
        dfs(r)
    return mapping