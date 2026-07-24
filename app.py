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


# ── GitHub에서 읽은 데이터를 st.session_state에 캐시 (세션당 1회) ──
# 쿼리 파라미터 ?refresh=1 로 강제 재조회 가능
force_refresh = st.query_params.get("refresh") == "1"
if force_refresh:
    st.query_params.clear()

if "gh_loaded" not in st.session_state or force_refresh:
    data, sha, err = gh_load()
    st.session_state["gh_data"] = data
    st.session_state["gh_sha"] = sha
    st.session_state["gh_error"] = err
    st.session_state["gh_loaded"] = True

data = st.session_state["gh_data"]
err = st.session_state["gh_error"]

# ── 세션 캐시된 데이터를 HTML에 직접 JSON으로 주입 (bidirectional 컴포넌트 없음) ──
with open(FRONTEND_HTML_PATH, "r", encoding="utf-8") as f:
    html = f.read()

html = html.replace("__INITIAL_DATA_JSON__", json.dumps(data))
html = html.replace("__LOAD_ERROR__", json.dumps(err))

components.html(html, height=950, scrolling=True)
