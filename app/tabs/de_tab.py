# app/tabs/de_tab.py

from pathlib import Path

import pandas as pd
import streamlit as st

from utils.model_recommend import recommend_age_model
from utils.r_runner import analyse_de_distribution
from utils.state_manager import (
    get_current_sample,
    get_sar_result,
    has_sar_result,
    set_de_dist_result,
    get_de_dist_result,
    has_de_dist_result,
)


# De 분포에 넣을 aliquot 집합 선택지. 기본은 QC 통과만.
# QC 미달을 넣을지 뺄지는 아직 확정되지 않은 설계 결정이라(계획서 항목 4),
# 여기서 강제하지 않고 연구자가 고르게 한 뒤 무엇을 썼는지 결과에 기록한다.
SOURCE_ACCEPTED = "QC 통과만"
SOURCE_ALL = "전체 (QC 미달 포함)"

# 추천 모델 한 줄 설명.
MODEL_BLURB = {
    "CAM": "Central Age Model — 잘 표백된 단일 집단의 중심 연령",
    "MAM": "Minimum Age Model — 부분 표백 시료의 최소(가장 젊은) 연령",
    "FMM": "Finite Mixture Model — 이산 혼합 집단의 성분별 연령",
}


def _collect_de(sar_result: dict, source_label: str) -> tuple[list, list, int]:
    """선택한 집합에서 De/오차 벡터를 뽑는다. 반환: (de, de_error, 집합 크기)."""
    if source_label == SOURCE_ACCEPTED:
        rows = sar_result.get("accepted", [])
    else:
        rows = sar_result.get("aliquots", [])

    de = [r["de"] for r in rows]
    de_error = [r["de_error"] for r in rows]
    return de, de_error, len(rows)


def _render_recommendation(rec: dict) -> None:
    model = rec["model"]

    st.markdown(f"### 추천 모델: `{model}`")
    st.caption(MODEL_BLURB.get(model, ""))

    for reason in rec["reasons"]:
        st.markdown(f"- {reason}")

    st.caption(
        "이 추천은 분포 지표에 문헌 기반 규칙을 적용한 가이드입니다. "
        "같은 입력·같은 임계값이면 항상 같은 모델이 나옵니다. 최종 선택은 연구자 판단입니다."
    )


def _render_descriptors(result: dict) -> None:
    col1, col2, col3, col4 = st.columns(4)

    col1.metric("aliquot 수", result["n"])
    col2.metric(
        "중심 De (Gy)",
        f"{result['central_de']:.1f}" if result["central_de"] is not None else "N/A",
    )
    col3.metric(
        "과분산 (OD)",
        f"{result['od_rel']:.1f}%" if result["od_rel"] is not None else "N/A",
    )
    col4.metric(
        "왜도",
        f"{result['skewness']:.2f}" if result["skewness"] is not None else "N/A",
    )

    if result.get("n_dropped"):
        st.caption(f"유효하지 않은 De {result['n_dropped']}개는 분석에서 제외했습니다.")


def _render_plots(result: dict) -> None:
    col1, col2 = st.columns(2)

    for col, key, caption in (
        (col1, "radial_plot_file", "Radial plot"),
        (col2, "abanico_plot_file", "Abanico plot"),
    ):
        plot_file = result.get(key)

        with col:
            if plot_file and Path(plot_file).exists():
                st.image(plot_file, caption=caption)
            else:
                st.info(f"{caption}가 없습니다.")


def _render_fmm(result: dict) -> None:
    fmm = result.get("fmm")

    if fmm is None:
        st.info(f"FMM(다봉성) 판정은 하지 못했습니다: {result.get('fmm_error')}")
        return

    # 성분 수 k별 BIC. k=1(단일)을 맨 위에 함께 놓아 다성분과 비교되게 한다.
    rows = [{"성분 수 k": 1, "BIC": fmm["single_bic"]}]
    rows += [{"성분 수 k": k, "BIC": b} for k, b in zip(fmm["k"], fmm["bic"])]

    st.markdown("**성분 수별 BIC** (낮을수록 선호)")
    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)

    bic_strong = result["recommendation"]["thresholds"]["bic_strong"]
    st.caption(
        f"최적 성분 수 k={fmm['best_k']} · 단일 대비 ΔBIC {fmm['delta_bic']:.1f} "
        f"(> {bic_strong:.0f}이면 다봉의 강한 근거) · sigmab={fmm['sigmab']:.2f}"
    )
    st.caption(
        "FMM 판정은 sigmab에 민감합니다. sigmab을 바꿔 다시 실행하면 판정이 달라질 수 있습니다."
    )


def _render_signals(rec: dict) -> None:
    with st.expander("판정 근거 상세 (재현용)", expanded=False):
        st.markdown("**신호 지표**")
        st.json(rec["signals"])
        st.markdown("**임계값 (문헌 기반 상수)**")
        st.json(rec["thresholds"])


def render_de_tab() -> None:
    """
    De Distribution 탭을 렌더링한다.

    역할:
        SAR에서 얻은 De 분포의 특성(과분산·왜도·다봉성)을 분석하고,
        문헌 기반 규칙으로 통계 연령모델(CAM/MAM/FMM)을 추천한다.
    """
    st.header("4. De Distribution")

    sample = get_current_sample()

    if sample is None:
        st.warning("먼저 `Data Upload & Inspect` 탭에서 BIN/RDA 파일을 업로드하세요.")
        return

    if not has_sar_result():
        st.warning("먼저 `SAR Analysis` 탭에서 SAR 분석을 실행해 De 값을 확보하세요.")
        return

    sar_result = get_sar_result()

    st.caption(
        "SAR에서 얻은 De 분포의 특성(과분산·왜도·다봉성)을 분석해 "
        "통계 연령모델(CAM/MAM/FMM)을 추천합니다."
    )

    st.divider()

    # ------------------------------------------------------------
    # 분석 입력: De 집합 + sigmab
    # ------------------------------------------------------------
    n_accepted = sar_result.get("n_accepted", 0)
    n_all = len(sar_result.get("aliquots", []))

    source_label = st.radio(
        "분석에 쓸 De 집합",
        options=[SOURCE_ACCEPTED, SOURCE_ALL],
        help="QC 미달 aliquot을 De 분포에 넣을지 여기서 정합니다. 무엇을 썼는지 결과에 기록됩니다.",
    )
    st.caption(f"QC 통과 {n_accepted}개 · 전체 {n_all}개")

    sigmab = st.number_input(
        "sigmab (FMM 성분 내 과분산 가정치)",
        min_value=0.01,
        max_value=1.0,
        value=0.15,
        step=0.01,
        help=(
            "FMM(다봉성) 판정이 이 값에 민감합니다. 잘 표백된 단일 성분의 과분산 "
            "추정치이며 보통 0.1~0.2를 씁니다. 사용한 값은 결과에 기록됩니다."
        ),
    )

    de, de_error, n_input = _collect_de(sar_result, source_label)
    n_valid = sum(1 for x in de if x is not None)

    if st.button("De 분포 분석 실행", type="primary"):
        if n_valid < 3:
            st.warning(
                f"De 분포 분석에는 최소 3개의 De가 필요합니다 (현재 {n_valid}개). "
                "SAR에서 aliquot을 더 확보하거나 De 집합을 바꿔 보세요."
            )
            return

        try:
            with st.spinner("De 분포 분석 중..."):
                analysis = analyse_de_distribution(
                    de=de,
                    de_error=de_error,
                    output_dir=sample["paths"]["curve_plot_dir"],
                    sigmab=float(sigmab),
                )

            recommendation = recommend_age_model(
                od_rel=analysis["od_rel"],
                skewness=analysis["skewness"],
                n=analysis["n"],
                fmm=analysis["fmm"],
            )

            result = {
                **analysis,
                "recommendation": recommendation,
                "de_source": source_label,
                "n_input": n_input,
            }

            set_de_dist_result(result)

        except Exception as e:
            st.error("De 분포 분석에 실패했습니다.")
            st.exception(e)
            return

    # ------------------------------------------------------------
    # 결과
    # ------------------------------------------------------------
    if not has_de_dist_result():
        return

    result = get_de_dist_result()

    st.divider()
    st.success(f"De 분포 분석 완료 — {result['de_source']} {result['n']}개 사용")

    _render_recommendation(result["recommendation"])

    st.divider()
    _render_descriptors(result)

    st.markdown("### 분포 시각화")
    _render_plots(result)

    st.markdown("### 다봉성 (FMM)")
    _render_fmm(result)

    _render_signals(result["recommendation"])

    with st.expander("원본 결과 보기", expanded=False):
        st.json(result)
