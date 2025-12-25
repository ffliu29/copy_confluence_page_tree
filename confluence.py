# confluence.py

import requests
import base64

BASE_URL = "https://dolphindb1.atlassian.net/wiki"


# =========================
# Session
# =========================
def get_session(username, api_token):
    auth_str = f"{username}:{api_token}"
    encoded = base64.b64encode(auth_str.encode("utf-8")).decode("ascii")
    session = requests.Session()
    session.headers.update({
        "Authorization": f"Basic {encoded}",
        "Content-Type": "application/json",
        "X-Atlassian-Token": "no-check"
    })
    return session


# =========================
# 获取页面（跨空间 / 读取标题用）
# =========================
def get_page_full(page_id, username, api_token):
    session = get_session(username, api_token)
    expand = (
        "title,body.storage,ancestors,"
        "restrictions.read.restrictions.user,"
        "restrictions.read.restrictions.group,"
        "restrictions.update.restrictions.user,"
        "restrictions.update.restrictions.group"
    )
    url = f"{BASE_URL}/rest/api/content/{page_id}?expand={expand}"
    r = session.get(url)
    if r.status_code != 200:
        raise RuntimeError(
            f"get_page_full failed {r.status_code}: {r.text}"
        )
    return r.json()


# =========================
# Create API（跨空间）
# =========================
def create_page(space_key, parent_id, title, content, username, api_token):
    session = get_session(username, api_token)
    payload = {
        "type": "page",
        "title": title,
        "ancestors": [{"id": str(parent_id)}],
        "space": {"key": space_key},
        "body": {
            "storage": {
                "value": content,
                "representation": "storage"
            }
        }
    }
    r = session.post(f"{BASE_URL}/rest/api/content", json=payload)
    r.raise_for_status()
    return r.json()


# =========================
# ⭐ Copy API（UI 等价）
# =========================
def copy_page_ui_equivalent(
    source_page_id,
    target_parent_id,
    username,
    api_token,
    new_title=None
):
    """
    与 Confluence UI『复制页面』等价：
    - 权限
    - 继承关系
    - 子页面
    """
    session = get_session(username, api_token)

    payload = {
        "destination": {
            "type": "parent_page",
            "value": str(target_parent_id)
        },
        "copyAttachments": True,
        "copyPermissions": True,
        "copyProperties": True,
        "copyLabels": True
    }

    if new_title:
        payload["titleOptions"] = {
            "replace": new_title
        }

    url = f"{BASE_URL}/rest/api/content/{source_page_id}/copy"
    r = session.post(url, json=payload)

    if r.status_code not in (200, 202):
        raise RuntimeError(
            f"Copy API failed {r.status_code}: {r.text}"
        )

    return r.json()


# =========================
# 页面索引（树构建）
# =========================
def get_all_pages(space_key, username, api_token):
    session = get_session(username, api_token)
    url = f"{BASE_URL}/rest/api/content/search"
    params = {
        "cql": f'space = "{space_key}" AND type = page',
        "limit": 100,
        "expand": "ancestors"
    }
    r = session.get(url, params=params)
    r.raise_for_status()
    return r.json().get("results", [])


def get_pages_by_ancestor(space_key, ancestor_id, username, api_token):
    session = get_session(username, api_token)
    url = f"{BASE_URL}/rest/api/content/search"
    params = {
        "cql": f'space = "{space_key}" AND type = page AND ancestor = "{ancestor_id}"',
        "limit": 100,
        "expand": "ancestors"
    }
    r = session.get(url, params=params)
    r.raise_for_status()

    results = r.json().get("results", [])
    parent = get_page_full(ancestor_id, username, api_token)
    results.append(parent)
    return results


# --- 请将这段代码粘贴到 confluence.py 的末尾 ---

def apply_page_restrictions(page_id, res_data, username, api_token):
    """
    手动将权限限制应用到新页面。
    这是解决克隆后权限丢失的核心逻辑。
    """
    if not isinstance(res_data, dict):
        return False
        
    session = get_session(username, api_token)
    success = False
    
    # 遍历查看(read)和编辑(update)权限
    for op in ['read', 'update']:
        op_info = res_data.get(op, {})
        # 兼容不同的 API 嵌套结构
        details = op_info.get('restrictions', op_info) if isinstance(op_info, dict) else {}
        
        # 提取用户和组
        users = [{"type": "known", "accountId": u.get("accountId")} 
                 for u in details.get("user", []) if isinstance(u, dict) and u.get("accountId")]
        groups = [{"type": "group", "name": g.get("name")} 
                  for g in details.get("group", []) if isinstance(g, dict) and g.get("name")]
        
        if users or groups:
            # 写入权限的专用路径
            put_url = f"{BASE_URL}/rest/api/content/{page_id}/restriction/byOperation/{op}"
            try:
                r = session.put(put_url, json={"user": users, "group": groups})
                if r.status_code in (200, 204):
                    success = True
            except Exception as e:
                print(f"权限写入异常: {e}")
                
    return success

def update_page_title(page_id, new_title, username, api_token):
    """
    强制更新页面标题（用于 Copy API 后修正标题）
    """
    session = get_session(username, api_token)

    # 先取当前版本号
    r = session.get(f"{BASE_URL}/rest/api/content/{page_id}?expand=version")
    r.raise_for_status()
    data = r.json()
    version = data["version"]["number"] + 1

    payload = {
        "id": page_id,
        "type": "page",
        "title": new_title,
        "version": {"number": version}
    }

    r = session.put(
        f"{BASE_URL}/rest/api/content/{page_id}",
        json=payload
    )
    r.raise_for_status()
    return r.json()
