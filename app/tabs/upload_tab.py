# app/tabs/upload_tab.py

from __future__ import annotations

from pathlib import Path

import streamlit as st

from utils.file_utils import save_uploaded_file
from utils.r_runner import inspect_uploaded_file
from utils.state_manager import (
    get_current_sample,
    get_position_result,
    has_current_sample,
    has_position_result,
    is_new_uploaded_file,
    set_current_sample,
    set_position_result,
)


# ============================================================
# 1. UI helper
# ============================================================

def _render_empty_upload_message() -> None:
    """
    파일이 아직 업로드되지 않았을 때 안내 메시지를 출력한다.
    """
    st.info("BIN/RDA/RData 파일을 업로드하면 POSITION 정보를 확인할 수 있습니다.")


def _render_sample_summary(sample: dict) -> None:
    """
    현재 업로드된 sample 정보를 출력한다.
    """
    st.success("파일 업로드 완료")

    col1, col2 = st.columns(2)

    with col1:
        st.write("샘플 ID")
        st.code(str(sample["sample_id"]))

    with col2:
        st.write("저장 폴더")
        st.code(str(sample["sample_dir"]))

    st.write("원본 파일 경로")
    st.code(str(sample["raw_path"]))


def _render_position_result(result: dict) -> None:
    """
    inspect_uploaded_file() 결과를 출력한다.
    """
    st.success("POSITION 확인 완료")

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("POSITION 개수", result.get("n_positions", "N/A"))

    with col2:
        st.metric("Metadata rows", result.get("n_metadata_rows", "N/A"))

    with col3:
        st.write("파일 타입")
        st.code(str(result.get("file_type", "N/A")))

    with col4:
        st.write("R 객체")
        st.code(str(result.get("object_name", "N/A")))

    st.divider()

    st.markdown("### POSITION 목록")
    st.write(result.get("positions", []))

    st.markdown("### Record types")
    st.write(result.get("record_types", []))

    st.markdown("### Metadata columns")
    st.write(result.get("metadata_columns", []))

    with st.expander("원본 결과 보기", expanded=False):
        st.json(result)


# ============================================================
# 2. Upload tab
# ============================================================

def render_upload_tab(output_dir: Path) -> None:
    """
    Upload & Inspect 탭을 렌더링한다.

    역할:
        1. BIN/RDA/RData 파일 업로드
        2. outputs/samples/{sample_id}/raw 아래에 파일 저장
        3. R pipeline으로 파일 구조 및 POSITION 정보 확인
        4. current_sample, position_result를 session_state에 저장
    """

    st.header("1. Upload & Inspect")
    st.caption("BIN/RDA/RData 파일을 업로드하고 POSITION 정보를 확인합니다.")

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    uploaded_file = st.file_uploader(
        "BIN/RDA/RData 파일을 업로드하세요",
        type=["bin", "BIN", "rda", "RDA", "rdata", "RData"],
        help="Risø BIN 파일 또는 RDA/RData 파일을 업로드합니다.",
    )

    if uploaded_file is None:
        _render_empty_upload_message()

        if has_current_sample():
            st.warning(
                "현재 session_state에는 이전 업로드 샘플이 남아 있습니다. "
                "새 파일을 업로드하거나 전체 초기화를 실행하세요."
            )

        return

    # ------------------------------------------------------------
    # 새 파일 업로드 감지
    # ------------------------------------------------------------
    if is_new_uploaded_file(uploaded_file.name):
        sample = save_uploaded_file(
            uploaded_file=uploaded_file,
            samples_dir=output_dir,
        )

        set_current_sample(
            sample=sample,
            uploaded_file_name=uploaded_file.name,
        )

    sample = get_current_sample()

    if sample is None:
        st.error("업로드된 샘플 정보를 불러오지 못했습니다.")
        return

    # ------------------------------------------------------------
    # 업로드 결과 표시
    # ------------------------------------------------------------
    _render_sample_summary(sample)

    st.divider()

    # ------------------------------------------------------------
    # POSITION 확인
    # ------------------------------------------------------------
    st.markdown("### POSITION 확인")

    st.write(
        "업로드된 파일을 R pipeline으로 읽고 metadata, record type, POSITION 정보를 확인합니다."
    )

    if st.button("POSITION 확인하기", type="primary"):
        try:
            with st.spinner("POSITION 정보를 확인하는 중입니다..."):
                result = inspect_uploaded_file(sample["raw_path"])

            set_position_result(result)

        except Exception as e:
            st.error("POSITION 확인 중 오류가 발생했습니다.")
            st.exception(e)

    # ------------------------------------------------------------
    # POSITION 결과 표시
    # ------------------------------------------------------------
    if has_position_result():
        result = get_position_result()
        _render_position_result(result)
    else:
        st.info("아직 POSITION 확인을 실행하지 않았습니다.")