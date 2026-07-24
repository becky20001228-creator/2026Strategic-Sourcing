import base64
import json
import os
import urllib.error
import urllib.request

import streamlit as st
import streamlit.components.v1 as components

st.set_page_config(
    page_title="RAmos Controller Hub",
    page_icon="🔧",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
  #MainMenu, header, footer { display: none !important; }
  .block-container { padding: 0 !important; max-width: 100% !important; }
  section[data-testid="stSidebar"] { display: none !important; }
</style>
""", unsafe_allow_html=True)

FRONTEND_HTML_PATH = os.path.join(os.path.dirname(__file__), "frontend", "index.html")

# ── GitHub API 설정 (토큰은 서버 쪽에만 존재, 클라이언트로 전달되지 않음) ──
GH_TOKEN = st.secrets["github"]["token"]
GH_REPO = st.secrets["github"]["repo"]
GH_PATH = "data/inventory.json"
GH_API = f"https://api.github.com/repos/{GH_REPO}/contents/{GH_PATH}"


def _gh_request(method, body=None):
    url = GH_API + ("?ref=main" if method == "GET" else "")
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {GH_TOKEN}")
    req.add_header("Accept", "application/vnd.github+json")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            payload = json.loads(e.read().decode("utf-8"))
        except Exception:
            payload = {}
        return e.code, payload
    except urllib.error.URLError as e:
        return 0, {"message": str(e.reason)}


def gh_load():
    """Returns (data_json_str_or_None, sha_or_None, error_message_or_None)."""
    status, payload = _gh_request("GET")
    if status == 404:
        return None, None, None
    if status < 200 or status >= 300:
        return None, None, payload.get("message", f"HTTP {status}")
    raw = base64.b64decode(payload["content"]).decode("utf-8")
    return raw, payload["sha"], None


def gh_save(data_str, sha):
    """Returns (new_sha_or_None, error_message_or_None)."""
    body = {
        "message": "Update inventory data via Controller Hub",
        "content": base64.b64encode(data_str.encode("utf-8")).decode("ascii"),
        "branch": "main",
    }
    if sha:
        body["sha"] = sha
    status, payload = _gh_request("PUT", body)
    if status < 200 or status >= 300:
        return None, f"{status}: {payload.get('message', 'unknown error')}"
    return payload["content"]["sha"], None


def gh_delete(sha):
    if not sha:
        return True, None
    body = {"message": "Reset inventory data via Controller Hub", "sha": sha, "branch": "main"}
    status, payload = _gh_request("DELETE", body)
    if status < 200 or status >= 300:
        return False, f"{status}: {payload.get('message', 'unknown error')}"
    return True, None


# ── 저장/초기화는 URL 쿼리 파라미터로 전달됨 (저장 버튼 클릭 시 전체 페이지 재이동) ──
hub_action = st.query_params.get("hub_action")
hub_payload = st.query_params.get("hub_payload")
if hub_action in ("save", "reset"):
    st.query_params.clear()

action_result = None
data = None
sha = None
err = None

if hub_action == "save" and hub_payload:
    _, current_sha, _ = gh_load()
    new_sha, save_err = gh_save(hub_payload, current_sha)
    if save_err and save_err.startswith("409"):
        # SHA가 오래됨 — 최신 SHA로 한 번만 재시도
        _, retry_sha, _ = gh_load()
        new_sha, save_err = gh_save(hub_payload, retry_sha)
    if save_err:
        action_result = {"ok": False, "type": "save", "message": save_err}
        data, sha, err = gh_load()
    else:
        action_result = {"ok": True, "type": "save"}
        data, sha = hub_payload, new_sha

elif hub_action == "reset":
    _, current_sha, _ = gh_load()
    ok, del_err = gh_delete(current_sha)
    action_result = {"ok": ok, "type": "reset"}
    if del_err:
        action_result["message"] = del_err

else:
    data, sha, err = gh_load()

with open(FRONTEND_HTML_PATH, "r", encoding="utf-8") as f:
    html = f.read()

html = html.replace("__INITIAL_DATA_JSON__", json.dumps(data))
html = html.replace("__LOAD_ERROR__", json.dumps(err))
html = html.replace("__ACTION_RESULT_JSON__", json.dumps(action_result))

components.html(html, height=950, scrolling=True)
