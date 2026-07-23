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

FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "frontend")
_controller_hub = components.declare_component("controller_hub", path=FRONTEND_DIR)

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


# ── 세션당 1회만 GitHub에서 로드 (이후에는 세션 상태 캐시 사용) ──
if "gh_loaded" not in st.session_state:
    data, sha, err = gh_load()
    st.session_state["gh_data"] = data
    st.session_state["gh_sha"] = sha
    st.session_state["gh_error"] = err
    st.session_state["gh_loaded"] = True

if "last_processed_nonce" not in st.session_state:
    st.session_state["last_processed_nonce"] = None
if "action_result" not in st.session_state:
    st.session_state["action_result"] = None

value = _controller_hub(
    initial_data=st.session_state["gh_data"],
    load_error=st.session_state["gh_error"],
    action_result=st.session_state["action_result"],
    key="controller_hub",
    default=None,
)

if (
    value
    and isinstance(value, dict)
    and value.get("nonce")
    and value.get("nonce") != st.session_state["last_processed_nonce"]
):
    action = value.get("action")
    nonce = value.get("nonce")
    st.session_state["last_processed_nonce"] = nonce

    if action == "save":
        payload_str = value.get("payload", "")
        new_sha, err = gh_save(payload_str, st.session_state["gh_sha"])
        if err and err.startswith("409"):
            # SHA가 오래됨 — 최신 SHA로 한 번만 재시도
            _, fresh_sha, _ = gh_load()
            new_sha, err = gh_save(payload_str, fresh_sha)
        if err:
            st.session_state["action_result"] = {"ok": False, "nonce": nonce, "message": err}
        else:
            st.session_state["gh_sha"] = new_sha
            st.session_state["gh_data"] = payload_str
            st.session_state["action_result"] = {"ok": True, "nonce": nonce}

    elif action == "reset":
        ok, err = gh_delete(st.session_state["gh_sha"])
        st.session_state["gh_sha"] = None
        st.session_state["gh_data"] = None
        st.session_state["action_result"] = {"ok": ok, "nonce": nonce, "message": err}

    st.rerun()
