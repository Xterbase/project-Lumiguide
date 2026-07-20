from pathlib import Path
import sys

import streamlit as st


# ------------------------------------------------------------
# prototype 파일에서 app/utils import 가능하게 경로 추가
# ------------------------------------------------------------
APP_DIR = Path(__file__).resolve().parents[1]
PROJECT_DIR = Path(__file__).resolve().parents[2]

if str(APP_DIR) not in sys.path:
    sys.path.append(str(APP_DIR))

from utils.r_runner import inspect_uploaded_file


st.set_page_config(
    page_title="LumiGuide Prototype 1",
    page_icon="💡",
    layout="wide",
)


st.title("Prototype 1: Load BIN/RDA/RData")
st.caption(
    "업로드된 BIN/RDA/RData 파일을 R pipeline으로 읽고 POSITION 정보를 확인합니다."
)


# ------------------------------------------------------------
# 업로드 폴더
# ------------------------------------------------------------
UPLOAD_DIR = PROJECT_DIR / "outputs" / "prototypes" / "version1" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


uploaded_file = st.file_uploader(
    "BIN/RDA/RData 파일 업로드",
    type=["bin", "rda", "rdata"],
)


if uploaded_file is None:
    st.info("파일을 업로드하면 R pipeline으로 파일 정보를 검사합니다.")
    st.stop()


# ------------------------------------------------------------
# 업로드 파일 저장
# ------------------------------------------------------------
saved_path = UPLOAD_DIR / uploaded_file.name

with open(saved_path, "wb") as f:
    f.write(uploaded_file.getbuffer())


st.success("파일 업로드 완료")
st.code(str(saved_path))


# ------------------------------------------------------------
# R pipeline 검사 실행
# ------------------------------------------------------------
if st.button("파일 검사 실행", type="primary"):
    try:
        result = inspect_uploaded_file(saved_path)

        st.subheader("파일 검사 결과")

        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.metric("File type", result["file_type"])

        with col2:
            st.metric("Object", result["object_name"])

        with col3:
            st.metric("Metadata rows", result["n_metadata_rows"])

        with col4:
            st.metric("Positions", result["n_positions"])

        st.divider()

        st.markdown("### 기본 정보")

        st.write("**파일명**")
        st.code(result["file"])

        st.write("**파일 경로**")
        st.code(result["file_path"])

        st.write("**Record types**")
        st.write(result["record_types"])

        st.markdown("### POSITION 목록")
        st.write(result["positions"])

        st.markdown("### Metadata columns")
        st.write(result["metadata_columns"])

        with st.expander("Raw result dict", expanded=False):
            st.json(result)

    except Exception as e:
        st.error("파일 검사 중 오류가 발생했습니다.")
        st.exception(e)