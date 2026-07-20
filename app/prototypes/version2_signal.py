from pathlib import Path
import sys

import pandas as pd
import streamlit as st


# ------------------------------------------------------------
# prototype 파일에서 app/utils import 가능하게 경로 추가
# ------------------------------------------------------------
APP_DIR = Path(__file__).resolve().parents[1]
PROJECT_DIR = Path(__file__).resolve().parents[2]

if str(APP_DIR) not in sys.path:
    sys.path.append(str(APP_DIR))

from utils.r_runner import (
    inspect_uploaded_file,
    inspect_rlum_records,
    generate_rlum_record_plot
)


st.set_page_config(
    page_title="LumiGuide Prototype 2",
    page_icon="💡",
    layout="wide",
)


st.title("Prototype 2: Signal Analysis")
st.caption(
    "업로드된 파일의 POSITION을 선택하고, 해당 POSITION의 RLum record 목록을 확인합니다."
)


# ------------------------------------------------------------
# 업로드 폴더
# ------------------------------------------------------------
UPLOAD_DIR = PROJECT_DIR / "outputs" / "prototypes" / "version2" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

PLOT_DIR = PROJECT_DIR / "outputs" / "prototypes" / "version2" / "plots"
PLOT_DIR.mkdir(parents=True, exist_ok=True)

uploaded_file = st.file_uploader(
    "BIN/RDA/RData 파일 업로드",
    type=["bin", "rda", "rdata", "RData"],
)


if uploaded_file is None:
    st.info("파일을 업로드하면 POSITION별 RLum record를 확인할 수 있습니다.")
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
# 1. POSITION 확인
# ------------------------------------------------------------
try:
    position_result = inspect_uploaded_file(saved_path)

except Exception as e:
    st.error("POSITION 확인 중 오류가 발생했습니다.")
    st.exception(e)
    st.stop()


st.subheader("1. POSITION 확인")

col1, col2, col3 = st.columns(3)

with col1:
    st.metric("File type", position_result["file_type"])

with col2:
    st.metric("Metadata rows", position_result["n_metadata_rows"])

with col3:
    st.metric("Positions", position_result["n_positions"])


positions = position_result["positions"]

selected_position = st.selectbox(
    "RLum record를 확인할 POSITION",
    positions,
)


# ------------------------------------------------------------
# 2. 선택한 POSITION의 record 확인
# ------------------------------------------------------------
st.subheader("2. POSITION별 record 확인")

if st.button("선택한 POSITION의 record 불러오기", type="primary"):
    try:
        records = inspect_rlum_records(
            saved_path,
            selected_position,
        )

        st.session_state["prototype2_records"] = records

    except Exception as e:
        st.error("RLum record 확인 중 오류가 발생했습니다.")
        st.exception(e)


if "prototype2_records" in st.session_state:
    records = st.session_state["prototype2_records"]

    st.success(
        f"POSITION {records['position']}에서 "
        f"{records['n_records']}개 record를 찾았습니다."
    )

    record_df = pd.DataFrame(
        {
            "record_index": records["record_index"],
            "metadata_index": records["metadata_index"],
            "record_type": records["record_type"],
            "dtype": records["dtype"],
            "comment": records["comment"],
            "run": records["run"],
            "set": records["set"],
            "irr_time": records["irr_time"],
            "npoints": records["npoints"],
            "low": records["low"],
            "high": records["high"],
            "an_temp": records["an_temp"],
            "an_time": records["an_time"],
            "light_source": records["light_source"],
        }
    )

    st.dataframe(record_df, use_container_width=True)

    selected_record = st.selectbox(
        "curve를 확인할 record",
        records["record_index"],
        format_func=lambda idx: records["record_label"][records["record_index"].index(idx)],
    )

    st.write("선택한 record index")
    st.code(str(selected_record))

    with st.expander("Raw records dict", expanded=False):
        st.json(records)


    # ------------------------------------------------------------
    # 3. 선택한 record의 curve plot 생성
    # ------------------------------------------------------------
    st.subheader("3. 선택한 record curve 확인")

    if st.button("선택한 record curve 생성", type="primary"):
        try:
            plot_result = generate_rlum_record_plot(
                path=saved_path,
                output_dir=PLOT_DIR,
                position=selected_position,
                record_index=selected_record,
            )

            st.session_state["prototype2_plot_result"] = plot_result

        except Exception as e:
            st.error("record curve 생성 중 오류가 발생했습니다.")
            st.exception(e)

    if "prototype2_plot_result" in st.session_state:
        plot_result = st.session_state["prototype2_plot_result"]
        plot_path = Path(plot_result["plot_file"])

        st.success("record curve 생성 완료")
        st.code(str(plot_path))

        if plot_path.exists():
            st.image(str(plot_path), caption="Selected RLum record curve")
        else:
            st.warning("plot 파일 경로는 반환되었지만 실제 파일을 찾지 못했습니다.")

        with st.expander("Raw plot result dict", expanded=False):
            st.json(plot_result)