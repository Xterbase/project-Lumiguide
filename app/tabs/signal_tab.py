# app/tabs/signal_tab.py

import streamlit as st

from utils.r_runner import inspect_rlum_records, generate_rlum_record_plot
from utils.state_manager import (
    get_current_sample,
    get_position_result,
    get_selected_signal_position,
    set_selected_signal_position,
    get_selected_record_info,
    reset_signal_position_outputs,
    reset_selected_record_outputs,
    set_rlum_records,
    get_rlum_records,
    has_rlum_records,
    set_selected_record_info,
    set_rlum_record_plot_result,
    get_rlum_record_plot_result,
    has_rlum_record_plot_result,
    set_signal_params,
    get_signal_params,
    has_signal_params,
)


def require_sample():
    sample = get_current_sample()

    if sample is None:
        st.warning("먼저 `Data Upload & Inspect` 탭에서 BIN/RDA 파일을 업로드하세요.")
        return None

    return sample


def require_position_result():
    result = get_position_result()

    if result is None:
        st.warning("먼저 `Data Upload & Inspect` 탭에서 POSITION 확인을 실행하세요.")
        return None

    return result


def build_record_rows(records: dict) -> list[dict]:
    return [
        {
            "record_index": records["record_index"][i],
            "LTYPE": records["record_type"][i],
            "DTYPE": records["dtype"][i],
            "COMMENT": records["comment"][i],
            "RUN": records["run"][i],
            "SET": records["set"][i],
            "IRR_TIME": records["irr_time"][i],
            "NPOINTS": records["npoints"][i],
            "LOW": records["low"][i],
            "HIGH": records["high"][i],
            "AN_TEMP": records["an_temp"][i],
            "AN_TIME": records["an_time"][i],
            "LIGHTSOURCE": records["light_source"][i],
        }
        for i in range(len(records["record_index"]))
    ]


def render_signal_tab():
    st.header("2. Signal Analysis")
    st.caption("POSITION별 record를 확인하고 signal/background integral을 설정합니다.")

    sample = require_sample()
    position_result = require_position_result()

    if sample is None or position_result is None:
        return

    positions = position_result["positions"]

    selected_position = st.selectbox(
        "감쇠곡선을 확인할 POSITION",
        positions,
        key="signal_position_selectbox",
    )

    if get_selected_signal_position() != selected_position:
        set_selected_signal_position(selected_position)
        reset_signal_position_outputs()

    if st.button("선택한 POSITION의 record 불러오기", type="primary"):
        try:
            with st.spinner(f"POSITION {selected_position}의 record 정보를 불러오는 중입니다..."):
                records = inspect_rlum_records(
                    sample["raw_path"],
                    selected_position,
                )

            set_rlum_records(records)
            st.success("Record 정보 불러오기 완료")

        except Exception as e:
            st.error("Record 정보를 불러오는 중 오류가 발생했습니다.")
            st.exception(e)

    st.divider()

    if not has_rlum_records():
        st.info("먼저 선택한 POSITION의 record 정보를 불러오세요.")
        return

    records = get_rlum_records()
    record_rows = build_record_rows(records)

    curve_types = sorted(set(row["LTYPE"] for row in record_rows))

    selected_curve_type = st.selectbox(
        "Curve type",
        ["ALL"] + curve_types,
        key="signal_curve_type_selectbox",
    )

    if selected_curve_type == "ALL":
        filtered_rows = record_rows
    else:
        filtered_rows = [
            row for row in record_rows
            if row["LTYPE"] == selected_curve_type
        ]

    if not filtered_rows:
        st.warning("선택한 curve type에 해당하는 record가 없습니다.")
        return

    col_left, col_right = st.columns([1, 2])

    with col_left:
        selected_record = st.selectbox(
            "Record 선택",
            filtered_rows,
            format_func=lambda row: (
                f"#{row['record_index']} | "
                f"{row['LTYPE']} | "
                f"{row['DTYPE']} | "
                f"{row['COMMENT']}"
            ),
            key="signal_record_selectbox",
        )

        if get_selected_record_info() != selected_record:
            set_selected_record_info(selected_record)
            reset_selected_record_outputs()

        if st.button("선택한 record curve 보기", type="primary"):
            try:
                with st.spinner(
                    f"POSITION {selected_position}, "
                    f"Record {selected_record['record_index']} curve 생성 중..."
                ):
                    plot_result = generate_rlum_record_plot(
                        sample["raw_path"],
                        sample["paths"]["curve_plot_dir"],
                        selected_position,
                        selected_record["record_index"],
                    )

                set_rlum_record_plot_result(plot_result)

            except Exception as e:
                st.error("Curve 이미지를 생성하는 중 오류가 발생했습니다.")
                st.exception(e)

        st.subheader("선택 record 정보")
        st.json(selected_record)

    with col_right:
        if has_rlum_record_plot_result():
            plot_result = get_rlum_record_plot_result()

            st.image(
                plot_result["plot_file"],
                caption=(
                    f"POSITION {plot_result['position']} / "
                    f"Record {plot_result['record_index']}"
                ),
            )

            st.write("저장 경로")
            st.code(plot_result["plot_file"])
        else:
            st.info("선택한 record의 curve 이미지가 여기에 표시됩니다.")

    st.divider()

    st.subheader("Filtered record metadata")
    st.dataframe(
        filtered_rows,
        use_container_width=True,
        hide_index=True,
    )

    st.divider()

    st.subheader("Integral 설정")

    col_signal, col_background = st.columns(2)

    with col_signal:
        signal_integral = st.text_input(
            "Signal integral",
            value="1:2",
            help="예: 1:2 또는 450:500",
            key="signal_integral_input",
        )

    with col_background:
        background_integral = st.text_input(
            "Background integral",
            value="900:1000",
            help="예: 900:1000",
            key="background_integral_input",
        )

    if st.button("현재 파라미터 저장"):
        set_signal_params(
            {
                "reference_position": selected_position,
                "reference_curve_type": selected_record["LTYPE"],
                "reference_record_index": selected_record["record_index"],
                "reference_record_comment": selected_record["COMMENT"],
                "signal_integral": signal_integral,
                "background_integral": background_integral,
            }
        )

        st.success("Signal parameter 저장 완료")

    if has_signal_params():
        st.write("저장된 파라미터")
        st.json(get_signal_params())