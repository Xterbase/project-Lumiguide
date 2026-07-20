# app/tabs/sar_tab.py

import pandas as pd
import streamlit as st

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
        st.metric("성공", result["n_success"])

    with col2:
        st.metric("실패", result["n_failed"])

    with col3:
        st.write("Signal integral")
        st.code(":".join(str(v) for v in result["signal_integral"]))

    with col4:
        st.write("Background integral")
        st.code(":".join(str(v) for v in result["background_integral"]))


def _render_aliquot_table(aliquots: list[dict]) -> None:
    df = pd.DataFrame(aliquots)

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

    st.dataframe(df, use_container_width=True, hide_index=True)


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
        st.warning("먼저 `Upload & Inspect` 탭에서 BIN/RDA 파일을 업로드하세요.")
        return

    position_result = get_position_result()

    if position_result is None:
        st.warning("먼저 `Upload & Inspect` 탭에서 POSITION을 확인하세요.")
        return

    params = _require_signal_params()

    if params is None:
        return

    st.caption(
        f"Signal integral `{params['signal_integral']}` / "
        f"Background integral `{params['background_integral']}` "
        f"(POSITION {params['reference_position']}의 곡선을 보고 정한 값)"
    )

    st.divider()

    # ------------------------------------------------------------
    # 분석 대상 POSITION 선택
    # ------------------------------------------------------------
    available = position_result.get("positions", [])

    st.subheader("분석 대상 POSITION")

    selected = st.multiselect(
        "SAR을 돌릴 POSITION",
        options=available,
        default=get_sar_target_positions() or available,
        help="De 분포를 만들려면 aliquot이 여러 개 필요합니다. 기본값은 전체입니다.",
        key="sar_target_positions_input",
    )

    if not selected:
        st.info("POSITION을 하나 이상 선택하세요.")
        return

    if st.button("SAR 분석 실행", type="primary"):
        set_sar_target_positions(selected)

        try:
            with st.spinner(f"POSITION {len(selected)}개 분석 중..."):
                result = run_sar_analysis(
                    path=sample["raw_path"],
                    positions=selected,
                    signal_integral=params["signal_integral"],
                    background_integral=params["background_integral"],
                )

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
        with st.expander(f"실패한 POSITION {result['n_failed']}개", expanded=True):
            for item in result["failed"]:
                st.write(f"**POSITION {item['position']}**")
                st.code(item["reason"])

    with st.expander("원본 결과 보기", expanded=False):
        st.json(result)
