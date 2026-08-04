# app/utils/model_recommend.py
"""De 분포 지표 -> CAM/MAM/FMM 추천 (결정적).

재현성 제약이 이 모듈의 존재 이유다. 같은 입력 + 같은 임계값이면 항상 같은 모델을
낸다. 임계값과 sigmab는 결과를 바꾸는 요인이므로 반환값(thresholds/signals)에 실어
기록에 남긴다 — SAR가 signal_params를 결과에 싣는 것과 같은 이유다(integral이 De를
바꾸듯, sigmab는 FMM 판정을 바꾼다. CA1 fixture: sigmab 0.15->FMM, 0.30->아님).

이 추천은 연구자 판단을 대체하지 않고 돕는 가이드다. 근거 지표를 함께 돌려주므로
연구자가 왜 그 모델인지 보고, 필요하면 임계값/sigmab를 바꿔 다시 볼 수 있다.
(프로젝트 원칙: "SAR는 분류하되 거르지 않는다"와 같은 태도 — 판정 근거를 감추지 않는다.)

통계 자체(OD, 왜도, FMM BIC)는 R(Luminescence)에서 계산해 넘어온다. 이 모듈은
그 지표를 문헌 기반 규칙으로 매핑하는 결정 로직만 담는다(순수 Python, R 불필요).

임계값 출처
-----------
- OD_LOW_PCT: 잘 표백된 시료도 흔히 ~20%까지 과분산을 보인다.
  Arnold & Roberts (2009); Galbraith & Roberts (2012, Quaternary Geochronology).
- BIC_STRONG: 다성분이 단일성분보다 "강하게" 선호될 최소 ΔBIC.
  Kass & Raftery (1995) 근사 등급에서 6~10 = strong evidence.
- SIGMAB_DEFAULT: FMM 성분 내 과분산 가정치. Roberts et al. (2000);
  Galbraith & Roberts (2012). 결과가 여기 민감하므로 연구자 조정 대상.
- 왜도 유의성: 왜도 표준오차 SES = sqrt(6n(n-1)/((n-2)(n+1)(n+3))) 의 2배를 임계로.
  부분 표백을 왜도로 진단하는 접근은 Bailey & Arnold (2006).
"""

import math

# --- 임계값 (문헌 근거, 결정적 계약) ---
OD_LOW_PCT = 20.0
BIC_STRONG = 6.0
SIGMAB_DEFAULT = 0.15


def _skewness_se(n: int) -> float:
    """표본 왜도의 표준오차(정규분포 가정). 표준 공식."""
    return math.sqrt(6 * n * (n - 1) / ((n - 2) * (n + 1) * (n + 3)))


def recommend_age_model(od_rel: float | None, skewness: float | None, n: int, fmm: dict | None = None) -> dict:
    """De 분포 지표 -> 추천 모델 + 근거.

    결정 트리 (OD 게이트 우선):
      1. OD < OD_LOW_PCT              -> CAM  (잘 표백된 단일 집단)
      2. (OD 높음) 양의 왜도 유의     -> MAM  (부분 표백: 비대칭 상향 꼬리)
      3. (OD 높음) 다봉(ΔBIC>강함)    -> FMM  (이산 혼합)
      4. 그 외                        -> CAM  (과분산 크나 구조 근거 없음)

    왜도(MAM)를 다봉(FMM)보다 먼저 본다: 양의 왜도는 부분 표백의 전형적 신호이고
    MAM이 이를 겨냥한 모델이다. 왜도가 뚜렷하지 않을 때 이산 성분(FMM)을 본다.
    이 순서는 문헌 근거의 휴리스틱이며 연구자가 signals를 보고 뒤집을 수 있다.

    fmm: fit_finite_mixture 결과 dict 또는 None(표본 부족 등으로 미적합).
         필요한 키: delta_bic, best_k, sigmab.
    반환: {model, reasons, signals, thresholds}
    """
    n = int(n)

    # OD 게이트가 트리 전체의 뿌리다. OD가 없으면(분산 없음 등) 판정 자체가 불가능하다.
    if od_rel is None:
        raise ValueError("OD(과분산)를 계산할 수 없어(분산 없음 등) 모델을 추천할 수 없습니다.")

    skew_crit = 2 * _skewness_se(n)
    # zero-variance 등으로 왜도가 None이면 부분 표백(MAM) 판정만 건너뛴다 — OD/FMM은 유효.
    skew_known = skewness is not None
    positively_skewed = bool(skew_known and skewness > skew_crit)
    dbic = fmm.get("delta_bic") if fmm else None
    multimodal = bool(dbic is not None and dbic > BIC_STRONG)

    reasons: list[str] = []

    if od_rel < OD_LOW_PCT:
        model = "CAM"
        reasons.append(f"과분산 {od_rel:.1f}% < {OD_LOW_PCT:.0f}% → 잘 표백된 단일 집단")
    elif positively_skewed:
        model = "MAM"
        reasons.append(
            f"과분산 {od_rel:.1f}% 높음 + 양의 왜도 {skewness:.2f} > 임계 {skew_crit:.2f} "
            f"→ 부분 표백(비대칭 상향 꼬리)"
        )
    elif multimodal:
        model = "FMM"
        reasons.append(
            f"과분산 높음, 유의한 왜도 없음, BIC가 성분 {fmm['best_k']}개를 단일 대비 "
            f"ΔBIC {fmm['delta_bic']:.1f}(>{BIC_STRONG:.0f})로 선호 → 이산 혼합"
        )
    else:
        model = "CAM"
        reasons.append(
            f"과분산 {od_rel:.1f}% 높으나 유의한 왜도·다봉 근거 없음 → CAM(과분산 큼에 유의)"
        )
        if fmm is None:
            reasons.append("FMM 미적합(표본 부족 등)으로 다봉성은 확인하지 못했습니다")

    if not skew_known and od_rel >= OD_LOW_PCT:
        reasons.append("왜도를 계산할 수 없어(분산 부족 등) 부분 표백(MAM) 판정은 건너뛰었습니다")

    return {
        "model": model,
        "reasons": reasons,
        "signals": {
            "od_rel": od_rel,
            "skewness": skewness,
            "skew_crit": skew_crit,
            "positively_skewed": positively_skewed,
            "multimodal": multimodal,
            "n": n,
            "fmm_delta_bic": (fmm.get("delta_bic") if fmm else None),
            "fmm_best_k": (fmm.get("best_k") if fmm else None),
            "sigmab": (fmm.get("sigmab") if fmm else None),
        },
        "thresholds": {
            "od_low_pct": OD_LOW_PCT,
            "bic_strong": BIC_STRONG,
            "sigmab_default": SIGMAB_DEFAULT,
        },
    }


# ============================================================
# 셀프 체크
# ============================================================
# 분기 트리 + 경계값이 있으므로 각 가지와 경계를 확인한다.
# 실행: venv/bin/python app/utils/model_recommend.py

if __name__ == "__main__":
    # fixture(ExampleData.DeValues, sigmab=0.15)에서 확인한 실제 지표로 회귀 고정.
    # CA1: OD 34.7%, skew -0.04, 다봉(ΔBIC 95.5) -> FMM
    ca1 = recommend_age_model(
        od_rel=34.69, skewness=-0.037, n=62,
        fmm={"delta_bic": 95.5, "best_k": 3, "sigmab": 0.15},
    )
    assert ca1["model"] == "FMM", ca1["model"]
    assert ca1["signals"]["multimodal"] is True

    # BT998: OD 8.0% -> OD 게이트에서 CAM. (왜도 1.34가 커도 OD가 낮으면 CAM이 맞다)
    bt = recommend_age_model(
        od_rel=8.02, skewness=1.34, n=25,
        fmm={"delta_bic": -6.4, "best_k": 2, "sigmab": 0.15},
    )
    assert bt["model"] == "CAM", bt["model"]

    # MAM 가지: 높은 OD + 유의한 양의 왜도. n=30 -> skew_crit ≈ 0.86.
    mam = recommend_age_model(od_rel=45.0, skewness=1.2, n=30, fmm={"delta_bic": 0.0, "best_k": 2, "sigmab": 0.15})
    assert mam["model"] == "MAM", mam["model"]

    # 높은 OD + 왜도 없음 + 다봉 아님 -> CAM 폴백
    fallback = recommend_age_model(od_rel=40.0, skewness=0.0, n=50, fmm={"delta_bic": 2.0, "best_k": 2, "sigmab": 0.15})
    assert fallback["model"] == "CAM", fallback["model"]
    assert fallback["signals"]["multimodal"] is False

    # 왜도(MAM)가 다봉(FMM)보다 우선: 둘 다 있으면 MAM.
    both = recommend_age_model(od_rel=50.0, skewness=1.5, n=40, fmm={"delta_bic": 50.0, "best_k": 3, "sigmab": 0.15})
    assert both["model"] == "MAM", both["model"]

    # fmm=None(FMM 미적합): 다봉 판정 불가 -> 폴백 CAM, 근거에 미적합 명시.
    no_fmm = recommend_age_model(od_rel=40.0, skewness=0.0, n=50, fmm=None)
    assert no_fmm["model"] == "CAM", no_fmm["model"]
    assert any("미적합" in r for r in no_fmm["reasons"])

    # skewness=None(zero-variance): MAM 판정은 건너뛰되 크래시하지 않는다.
    #   OD 낮음 -> CAM 게이트.
    skew_none_cam = recommend_age_model(od_rel=8.0, skewness=None, n=50, fmm=None)
    assert skew_none_cam["model"] == "CAM", skew_none_cam["model"]
    #   OD 높음 + 다봉 -> FMM (왜도 없이도 도달), 근거에 MAM 건너뜀 명시.
    skew_none_fmm = recommend_age_model(
        od_rel=40.0, skewness=None, n=50, fmm={"delta_bic": 99.0, "best_k": 3, "sigmab": 0.15}
    )
    assert skew_none_fmm["model"] == "FMM", skew_none_fmm["model"]
    assert any("건너뛰" in r for r in skew_none_fmm["reasons"])

    # delta_bic=None(FMM 실패 잔재): 다봉 판정 불가로 취급, 크래시 없음.
    dbic_none = recommend_age_model(
        od_rel=40.0, skewness=0.0, n=50, fmm={"delta_bic": None, "best_k": None, "sigmab": 0.15}
    )
    assert dbic_none["model"] == "CAM" and dbic_none["signals"]["multimodal"] is False

    # od_rel=None(OD 계산 불가): 트리 뿌리가 없으므로 명시적 에러.
    try:
        recommend_age_model(od_rel=None, skewness=0.0, n=50, fmm=None)
        assert False, "od_rel=None은 ValueError여야 한다"
    except ValueError:
        pass

    # 결정성: 같은 입력 두 번 -> 같은 결과.
    a = recommend_age_model(od_rel=34.69, skewness=-0.037, n=62, fmm={"delta_bic": 95.5, "best_k": 3, "sigmab": 0.15})
    assert a["model"] == ca1["model"], "같은 입력에 다른 모델이 나왔다"

    # 경계값: OD가 정확히 임계면 CAM 아님(< 만 CAM). OD==20.0 -> 게이트 통과.
    edge_od = recommend_age_model(od_rel=OD_LOW_PCT, skewness=0.0, n=50, fmm={"delta_bic": 0.0, "best_k": 2, "sigmab": 0.15})
    assert edge_od["model"] == "CAM", "OD==임계는 폴백 CAM이어야 한다"
    assert edge_od["signals"]["od_rel"] == OD_LOW_PCT
    # OD가 임계 바로 아래면 게이트 CAM (근거 문구가 게이트임을 보여야 함)
    below = recommend_age_model(od_rel=OD_LOW_PCT - 0.01, skewness=2.0, n=50, fmm={"delta_bic": 99.0, "best_k": 3, "sigmab": 0.15})
    assert below["model"] == "CAM" and "단일 집단" in below["reasons"][0]

    print("model_recommend self-check OK")
