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
# 6. Sidebar
# ============================================================

with st.sidebar:
    st.header("LumiGuide")

    st.markdown(
        """
        **Workflow**

        1. Data Upload & Inspect  
        2. Signal Analysis  
        3. SAR Analysis  
        4. De Distribution  
        5. Model Recommendation  
        """
    )

    st.divider()

    if st.button("전체 초기화", type="secondary"):
        reset_all_state()
        st.rerun()


# ============================================================
# 7. Main Tabs
# ============================================================

# 탭 번호는 사이드바 Workflow 목록과 일치해야 한다.
# (De Distribution 탭이 빠져 있어서 Model Recommendation이 4번으로 밀려 있었다)
tab_upload, tab_signal, tab_sar, tab_de, tab_model = st.tabs(
    [
        "1. Data Upload & Inspect",
        "2. Signal Analysis",
        "3. SAR Analysis",
        "4. De Distribution",
        "5. Model Recommendation",
    ]
)


with tab_upload:
    render_upload_tab(OUTPUT_DIR)


with tab_signal:
    render_signal_tab()


with tab_sar:
    render_sar_tab()


with tab_de:
    st.header("4. De Distribution")
    st.info("SAR 결과의 De 분포 분석 기능은 다음 단계에서 연결합니다.")


with tab_model:
    st.header("5. Model Recommendation")
    st.info("De distribution 기반 모델 추천 기능은 다음 단계에서 연결합니다.")