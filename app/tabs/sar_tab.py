# app/tabs/sar_tab.py

from pathlib import Path

import pandas as pd
import streamlit as st

from utils.file_utils import save_sar_results
from utils.r_runner import run_sar_analysis
from utils.state_manager import (
    get_current_sample,
    get_position_result,
    get_signal_params,
    has_signal_params,
    set_sar_target_positions,
    get_sar_target_positions,
    set_sar_result,
    get_sar_result,
    has_sar_result,
)


# POSITION 목록 맨 위에 넣는 전체 선택 항목.
# POSITION은 정수라 문자열 항목과 섞여도 값이 충돌하지 않는다.
SELECT_ALL = "전체 선택"


def _require_signal_params():
    """
    SAR은 Signal 단계에서 정한 integral 없이는 돌릴 수 없다.

    이 값을 여기서 다시 입력받게 하면 Signal 탭에서 곡선을 보고 정한 값과
    어긋날 수 있으므로, 저장된 값만 쓰고 없으면 되돌려 보낸다.
    """
    if not has_signal_params():
        st.warning(
            "먼저 `Signal Analysis` 탭에서 곡선을 확인하고 "
            "`현재 파라미터 저장`으로 signal/background integral을 정하세요."
        )
        return None

    return get_signal_params()


def _render_summary(result: dict) -> None:
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("품질 통과", result["n_accepted"])

    with col2:
        st.metric("품질 미달", result["n_rejected"])

    with col3:
        st.metric("분석 실패", result["n_failed"])

    with col4:
        st.write("Integral (signal / background)")
        st.code(
            f"{':'.join(str(v) for v in result['signal_integral'])}"
            f"  /  "
            f"{':'.join(str(v) for v in result['background_integral'])}"
        )


def _render_aliquot_table(aliquots: list[dict]) -> None:
    df = pd.DataFrame(aliquots)

    df = df.drop(columns=["plot_file"], errors="ignore")

    df = df.rename(
        columns={
            "position": "POSITION",
            "de": "De (Gy)",
            "de_error": "De error",
            "rc_status": "품질",
            "fit": "Fit",
            "n_n": "n/N",
            "recycling_ratio": "Recycling ratio",
            "recuperation": "Recuperation",
        }
    )

    st.dataframe(df, width="stretch", hide_index=True)


def _render_position_detail(result: dict) -> None:
    """
    POSITION 하나를 골라 De / QC 전 항목 / dose-response plot을 함께 본다.

    표만 보면 De 값이 타당한지 판단할 근거가 없다.
    성장곡선을 눈으로 확인할 수 있어야 결과를 신뢰할 수 있다.
    """
    aliquots = result["aliquots"]
    by_position = {a["position"]: a for a in aliquots}

    # 값은 aliquot이 아니라 POSITION 번호이고 조회는 항상 현재 result로 하므로,
    # key를 둬도 옛 결과를 가리키지 않는다.
    selected = st.selectbox(
        "POSITION 상세",
        options=sorted(by_position.keys()),
        key="sar_detail_position",
    )

    aliquot = by_position[selected]

    col_left, col_right = st.columns([1, 2])

    with col_left:
        st.metric("De (Gy)", f"{aliquot['de']:.1f}" if aliquot["de"] else "N/A")
        st.metric(
            "De error",
            f"{aliquot['de_error']:.1f}" if aliquot["de_error"] else "N/A",
        )

        status = str(aliquot["rc_status"]).upper()

        if status == "FAILED":
            st.error(f"품질: {aliquot['rc_status']}")
        else:
            st.success(f"품질: {aliquot['rc_status']}")

        st.caption(f"Fit: {aliquot['fit']}")

    with col_right:
        plot_file = aliquot.get("plot_file")

        if plot_file and Path(plot_file).exists():
            st.image(plot_file, caption=f"POSITION {selected} dose-response")
        else:
            st.info("이 POSITION의 dose-response plot이 없습니다.")

    qc_rows = [q for q in result.get("qc_rows", []) if q["position"] == selected]

    if qc_rows:
        st.markdown("**품질 기준 상세**")

        qc_df = pd.DataFrame(qc_rows).drop(columns=["position"])
        qc_df = qc_df.rename(
            columns={
                "criteria": "기준",
                "value": "측정값",
                "threshold": "임계값",
                "status": "판정",
            }
        )

        st.dataframe(qc_df, width="stretch", hide_index=True)


def render_sar_tab() -> None:
    """
    SAR Analysis 탭을 렌더링한다.

    역할:
        Signal 단계에서 정한 integral로 POSITION별 SAR을 돌려 De를 얻는다.
        여기서 나온 De 모음이 다음 단계(De 분포 -> 모델 추천)의 입력이다.
    """
    st.header("3. SAR Analysis")

    sample = get_current_sample()

    if sample is None:
        st.warning("먼저 `Data Upload & Inspect` 탭에서 BIN/RDA 파일을 업로드하세요.")
        return

    position_result = get_position_result()

    if position_result is None:
        st.warning("먼저 `Data Upload & Inspect` 탭에서 POSITION을 확인하세요.")
        return

    params = _require_signal_params()

    if params is None:
        return

    st.caption(
        "Signal Analysis에서 설정한 integral을 사용하여 "
        "선택한 POSITION에 대해 SAR 분석을 수행합니다."
    )

    st.markdown(
        f"**사용자 설정 값:**　"
        f"Signal integral `{params['signal_integral']}`　/　"
        f"Background integral `{params['background_integral']}`"
    )

    st.caption(f"POSITION {params['reference_position']}의 곡선을 보고 정한 값입니다.")

    st.divider()

    # ------------------------------------------------------------
    # 분석 대상 POSITION 선택
    # ------------------------------------------------------------
    available = position_result.get("positions", [])

    st.subheader("분석 대상 POSITION")

    # 기본값을 전체로 두면 무심코 실행했을 때 전 POSITION이 돌아간다.
    # 비워두고, 대신 목록 맨 위에 전체 선택 항목을 둔다.
    picked = st.multiselect(
        "SAR을 돌릴 POSITION",
        options=[SELECT_ALL] + list(available),
        default=[],
        placeholder="(선택 안 함)",
        help="De 분포를 만들려면 aliquot이 여러 개 필요합니다.",
    )

    if SELECT_ALL in picked:
        selected = list(available)
    else:
        selected = picked

    if not selected:
        st.info("POSITION을 하나 이상 선택하세요.")
        return

    if SELECT_ALL in picked:
        st.caption(f"전체 {len(selected)}개 POSITION이 선택되었습니다.")

    if st.button("SAR 분석 실행", type="primary"):
        set_sar_target_positions(selected)

        paths = sample["paths"]

        try:
            with st.spinner(f"POSITION {len(selected)}개 분석 중..."):
                result = run_sar_analysis(
                    path=sample["raw_path"],
                    positions=selected,
                    signal_integral=params["signal_integral"],
                    background_integral=params["background_integral"],
                    plot_dir=paths["curve_plot_dir"],
                )

            # 분석과 저장을 분리한다. 저장이 실패해도 화면의 결과는 살린다.
            try:
                saved = save_sar_results(paths["analysis_results_dir"], result)
                result["saved_files"] = {k: str(v) for k, v in saved.items()}
            except Exception as e:
                result["saved_files"] = {}
                st.warning(f"결과 CSV 저장에 실패했습니다: {e}")

            set_sar_result(result)

        except Exception as e:
            st.error("SAR 분석에 실패했습니다.")
            st.exception(e)
            return

    # ------------------------------------------------------------
    # 결과
    # ------------------------------------------------------------
    if not has_sar_result():
        return

    result = get_sar_result()

    st.divider()
    st.success(f"SAR 분석 완료 — De {result['n_success']}개 확보")

    _render_summary(result)

    st.markdown("### Aliquot별 결과")
    _render_aliquot_table(result["aliquots"])

    # 실패한 POSITION은 조용히 빠뜨리지 않고 사유와 함께 보여준다.
    # 몇 개가 왜 빠졌는지 모르면 De 분포의 표본 수를 신뢰할 수 없다.
    if result["n_failed"] > 0:
        with st.expander(f"분석 실패 {result['n_failed']}개", expanded=True):
            for item in result["failed"]:
                st.write(f"**POSITION {item['position']}**")
                st.code(item["reason"])

    st.divider()

    st.markdown("### POSITION 상세")
    _render_position_detail(result)

    st.divider()

    saved_files = result.get("saved_files") or {}

    if saved_files:
        st.markdown("### 저장된 결과")
        st.caption(
            "분석 결과는 sample 폴더에 저장됩니다. "
            "앱을 껐다 켜도 남고, 다음 단계나 외부 도구로 넘길 수 있습니다."
        )

        for name, file_path in saved_files.items():
            st.code(file_path)

    with st.expander("원본 결과 보기", expanded=False):
        st.json(result)
