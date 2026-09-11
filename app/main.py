# app/main.py

from __future__ import annotations

from pathlib import Path
import sys

import streamlit as st


# ============================================================
# 0. Path 설정
# ============================================================

APP_DIR = Path(__file__).resolve().parent
PROJECT_DIR = APP_DIR.parent

if str(APP_DIR) not in sys.path:
    sys.path.append(str(APP_DIR))


# ============================================================
# 1. 내부 모듈 import
# ============================================================

from tabs.upload_tab import render_upload_tab
from tabs.signal_tab import render_signal_tab
from tabs.sar_tab import render_sar_tab
from tabs.de_tab import render_de_tab
from utils.state_manager import init_session_state, reset_all_state


# ============================================================
# 2. Streamlit 기본 설정
# ============================================================

st.set_page_config(
    page_title="LumiGuide",
    page_icon="💡",
    layout="wide",
)


# ============================================================
# 3. session_state 초기화
# ============================================================

init_session_state()


# ============================================================
# 4. 기본 경로
# ============================================================

OUTPUT_DIR = PROJECT_DIR / "outputs" / "samples"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================
# 5. App Header
# ============================================================

st.title("LumiGuide")
st.caption(
    "Luminescence dating workflow assistant: "
    "data upload, signal analysis, SAR analysis, and model recommendation."
)


# ============================================================
# 6. Workflow 단계 정의
# ============================================================
# 사이드바 목록과 탭 라벨은 이 리스트 하나에서 만든다.
# 예전에 두 곳에 따로 적어두는 바람에 번호가 어긋난 적이 있다
# (De Distribution 탭이 빠져서 Model Recommendation이 4번을 차지했다).

WORKFLOW_STEPS = [
    "1. Data Upload & Inspect",
    "2. Signal Analysis",
    "3. SAR Analysis",
    "4. De Distribution",
    "5. Model Recommendation",
]

# st.tabs()의 key. 여기에 탭 라벨을 넣고 rerun하면 그 탭이 활성화된다.
#
# 주의: st.tabs()는 key만 줘서는 session_state와 연결되지 않는다.
# 구현상 on_change가 기본값 "ignore"이면 위젯으로 등록되지 않아서
# session_state[key]에 값을 넣어도 탭이 그 값을 읽지 않는다.
# 사이드바에서 탭을 바꾸려면 on_change="rerun"이 반드시 필요하다.
ACTIVE_TAB_KEY = "active_workflow_tab"


# ============================================================
# 7. Sidebar
# ============================================================
# 버튼 텍스트는 기본이 가운데 정렬이고 이를 바꾸는 옵션이 없어서 CSS로 처리한다.
# Streamlit 내부 DOM에 기대는 코드이므로 버전이 올라가면 깨질 수 있다.
# (깨져도 정렬만 가운데로 돌아갈 뿐 기능에는 영향이 없다)

st.markdown(
    """
    <style>
    section[data-testid="stSidebar"] .stButton > button,
    section[data-testid="stSidebar"] .stButton > button > div {
        justify-content: flex-start;
        text-align: left;
    }
</style>
    """,
    unsafe_allow_html=True,
)

with st.sidebar:
    st.header("LumiGuide")

    st.caption("Workflow")

    for step in WORKFLOW_STEPS:
        # 현재 탭은 눌린 것처럼 보이게 해서 어디에 있는지 알 수 있게 한다.
        is_active = st.session_state.get(ACTIVE_TAB_KEY) == step

        if st.button(
            step,
            key=f"nav_{step}",
            width="stretch",
            type="primary" if is_active else "tertiary",
        ):
            st.session_state[ACTIVE_TAB_KEY] = step
            st.rerun()

    st.divider()

    if st.button("전체 초기화", type="secondary"):
        reset_all_state()
        st.rerun()


# ============================================================
# 8. Main Tabs
# ============================================================

tab_upload, tab_signal, tab_sar, tab_de, tab_model = st.tabs(
    WORKFLOW_STEPS,
    key=ACTIVE_TAB_KEY,
    on_change="rerun",
)


# on_change="rerun"으로 tabs를 상태 위젯으로 만들었으면 .open으로 골라 렌더링해야
# 한다. 이걸 빼먹으면 매 rerun마다 5개 탭 본문이 전부 다시 실행되고, 그중 하나가
# (예: signal 탭의 selectbox) 위젯을 새로 등록/해제하면서 탭 컨테이너가 프론트엔드에서
# remount되어 다른 탭에서 위젯을 조작해도 화면이 이전 탭으로 튕겨나간다.
with tab_upload:
    if tab_upload.open:
        render_upload_tab(OUTPUT_DIR)


with tab_signal:
    if tab_signal.open:
        render_signal_tab()


with tab_sar:
    if tab_sar.open:
        render_sar_tab()


with tab_de:
    if tab_de.open:
        render_de_tab()


with tab_model:
    if tab_model.open:
        st.header("5. Model Recommendation")
        st.info("De distribution 기반 모델 추천 기능은 다음 단계에서 연결합니다.")