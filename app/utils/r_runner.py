import math
from pathlib import Path
from threading import Lock

import rpy2.robjects as ro
from rpy2 import rinterface
from rpy2.robjects import default_converter


# ========================================================================================================================

# 1. 경로 설정 및 기본 함수
## 프로젝트 경로 설정
BASE_DIR = Path(__file__).resolve().parents[2]
R_PIPELINE_PATH = BASE_DIR / "R" / "pipeline.R"


## rpy2를 위한 안전설정
R_LOCK = Lock()
_PIPELINE_LOADED = False


## VECTOR -> LIST
def r_vector_to_list(r_vector) -> list:
    if r_vector is None:
        return []

    if type(r_vector).__name__ == "NULLType":
        return []

    return list(r_vector)


# ========================================================================================================================

# 2. R NA -> Python None 변환
#
# rpy2는 R의 NA를 None이 아니라 타입별 sentinel 객체로 준다.
# 그대로 int()/str()를 씌우면 값이 조용히 오염된다.
#
#   int(NA_integer_)   -> -2147483648
#   str(NA_character_) -> "NA_character_"   (NACharacterType은 str의 서브클래스라 걸러지지 않는다)
#   NA_real_           -> float("nan")
#
# 그래서 sentinel은 반드시 `is` 동일성으로 판별해야 한다.

_R_NA_SENTINELS = (
    rinterface.NA_Character,
    rinterface.NA_Integer,
    rinterface.NA_Logical,
    rinterface.NA_Real,
)


def is_r_na(value) -> bool:
    if value is None:
        return True

    if any(value is na for na in _R_NA_SENTINELS):
        return True

    if isinstance(value, float) and math.isnan(value):
        return True

    return False


def r_int_list(r_vector) -> list[int | None]:
    return [
        None if is_r_na(x) else int(x)
        for x in r_vector_to_list(r_vector)
    ]


def r_float_list(r_vector) -> list[float | None]:
    return [
        None if is_r_na(x) else float(x)
        for x in r_vector_to_list(r_vector)
    ]


def r_str_list(r_vector) -> list[str | None]:
    return [
        None if is_r_na(x) else str(x)
        for x in r_vector_to_list(r_vector)
    ]


def r_scalar_int(r_vector) -> int | None:
    values = r_int_list(r_vector)
    return values[0] if values else None


def r_scalar_str(r_vector) -> str | None:
    values = r_str_list(r_vector)
    return values[0] if values else None


def r_scalar_float(r_vector) -> float | None:
    values = r_float_list(r_vector)
    return values[0] if values else None


# ========================================================================================================================

# version1: upload data
## R pipeline.R 파일 로드
def load_r_pipeline() -> None:
    """
    R/pipeline.R 파일을 R 환경에 source 한다.
    여러 번 호출되어도 한 번만 로드되도록 처리한다.
    """
    global _PIPELINE_LOADED

    if _PIPELINE_LOADED:
        return
    

    if not R_PIPELINE_PATH.exists():
        raise FileNotFoundError(f"pipeline.R을 찾을 수 없습니다: {R_PIPELINE_PATH}")

    r_path = R_PIPELINE_PATH.as_posix()

    with R_LOCK:
        if _PIPELINE_LOADED:
            return

        with default_converter.context():
            ro.r["source"](r_path)

        _PIPELINE_LOADED = True


## R의 inspect_positions() 호출 후 Python dict로 변환
def inspect_uploaded_file(path: str | Path) -> dict:
    """
    업로드된 BIN/RDA/RData 파일을 R 함수 inspect_positions()로 검사한다.

    R pipeline:
    - inspect_positions(path)
      - 내부에서 load_bin_data(path) 호출
      - 파일 정보, POSITION 정보, record type 정보 반환

    Python return:
    - Streamlit에서 바로 쓰기 좋은 dict
    """
    load_r_pipeline()

    file_path = Path(path).resolve()

    if not file_path.exists():
        raise FileNotFoundError(f"업로드 파일을 찾을 수 없습니다: {file_path}")

    r_file_path = file_path.as_posix()

    with R_LOCK:
        with default_converter.context():
            result = ro.r["inspect_positions"](r_file_path)

            file_name = r_scalar_str(result.rx2("file"))
            file_path_result = r_scalar_str(result.rx2("file_path"))
            file_type = r_scalar_str(result.rx2("file_type"))
            object_name = r_scalar_str(result.rx2("object_name"))
            n_candidates = r_scalar_int(result.rx2("n_candidates"))
            ignored_objects = r_str_list(result.rx2("ignored_objects"))

            n_metadata_rows = r_scalar_int(result.rx2("n_metadata_rows"))
            metadata_columns = r_str_list(result.rx2("metadata_columns"))

            n_positions = r_scalar_int(result.rx2("n_positions"))
            positions = r_int_list(result.rx2("positions"))

            record_types = r_str_list(result.rx2("record_types"))

    return {
        "file": file_name,
        "file_path": file_path_result,
        "file_type": file_type,
        "object_name": object_name,
        "n_candidates": n_candidates,
        "ignored_objects": ignored_objects,
        "n_metadata_rows": n_metadata_rows,
        "metadata_columns": metadata_columns,
        "n_positions": n_positions,
        "positions": positions,
        "record_types": record_types,
    }

def inspect_rlum_records(path: str | Path, position: int) -> dict:
    """
    선택한 POSITION의 RLum record 목록을 R 함수 inspect_rlum_records_by_position()로 조회한다.

    R pipeline:
    - inspect_rlum_records_by_position(path, pos)
      - 내부에서 load_bin_data(path) 호출
      - POSITION에 해당하는 metadata row와 RLum record 정보를 반환

    Python return:
    - Streamlit에서 record table/selectbox에 바로 쓰기 좋은 dict
    """
    load_r_pipeline()

    file_path = Path(path).resolve()

    if not file_path.exists():
        raise FileNotFoundError(f"업로드 파일을 찾을 수 없습니다: {file_path}")

    r_file_path = file_path.as_posix()
    position = int(position)

    with R_LOCK:
        with default_converter.context():
            result = ro.r["inspect_rlum_records_by_position"](
                r_file_path,
                position,
            )

            r_position = r_scalar_int(result.rx2("position"))
            n_records = r_scalar_int(result.rx2("n_records"))

            record_index = r_int_list(result.rx2("record_index"))
            metadata_index = r_int_list(result.rx2("metadata_index"))

            record_type = r_str_list(result.rx2("record_type"))
            dtype = r_str_list(result.rx2("dtype"))
            comment = r_str_list(result.rx2("comment"))

            run = r_int_list(result.rx2("run"))
            set_no = r_int_list(result.rx2("set"))
            irr_time = r_float_list(result.rx2("irr_time"))
            npoints = r_int_list(result.rx2("npoints"))

            low = r_float_list(result.rx2("low"))
            high = r_float_list(result.rx2("high"))
            an_temp = r_float_list(result.rx2("an_temp"))
            an_time = r_float_list(result.rx2("an_time"))

            light_source = r_str_list(result.rx2("light_source"))
            record_label = r_str_list(result.rx2("record_label"))

    return {
        "position": r_position,
        "n_records": n_records,
        "record_index": record_index,
        "metadata_index": metadata_index,
        "record_type": record_type,
        "dtype": dtype,
        "comment": comment,
        "run": run,
        "set": set_no,
        "irr_time": irr_time,
        "npoints": npoints,
        "low": low,
        "high": high,
        "an_temp": an_temp,
        "an_time": an_time,
        "light_source": light_source,
        "record_label": record_label,
    }

def generate_rlum_record_plot(
    path: str | Path,
    output_dir: str | Path,
    position: int,
    record_index: int,
) -> dict:
    """
    선택한 POSITION의 특정 record 하나를 plot_RLum으로 PNG 저장한다.

    R pipeline:
    - save_rlum_record_plot(path, pos, record_index, output_dir)
    """
    load_r_pipeline()

    file_path = Path(path).resolve()
    output_dir = Path(output_dir).resolve()

    if not file_path.exists():
        raise FileNotFoundError(f"업로드 파일을 찾을 수 없습니다: {file_path}")

    output_dir.mkdir(parents=True, exist_ok=True)

    with R_LOCK:
        with default_converter.context():
            result = ro.r["save_rlum_record_plot"](
                file_path.as_posix(),
                int(position),
                int(record_index),
                output_dir.as_posix(),
            )

            position_value = r_scalar_int(result.rx2("position"))
            record_index_value = r_scalar_int(result.rx2("record_index"))
            plot_file = r_scalar_str(result.rx2("plot_file"))

    return {
        "position": position_value,
        "record_index": record_index_value,
        "plot_file": plot_file,
    }


def run_sar_analysis(
    path: str | Path,
    positions: list[int],
    signal_integral: str,
    background_integral: str,
    plot_dir: str | Path | None = None,
) -> dict:
    """
    선택한 POSITION들에 대해 SAR 분석을 일괄 실행하고 De 값을 얻는다.

    R pipeline:
    - run_sar_analysis(path, positions, signal_integral, background_integral)
      - integral 문자열 파싱/검증은 R에서 수행
      - POSITION 하나가 실패해도 나머지는 계속 진행하고, 실패 사유를 따로 반환

    Python return:
    - aliquots: POSITION별 결과 행 리스트 (De 분포 단계의 입력)
    - failed:   실패한 POSITION과 사유
    """
    load_r_pipeline()

    file_path = Path(path).resolve()

    if not file_path.exists():
        raise FileNotFoundError(f"업로드 파일을 찾을 수 없습니다: {file_path}")

    if not positions:
        raise ValueError("분석할 POSITION이 선택되지 않았습니다.")

    if plot_dir is not None:
        plot_dir = Path(plot_dir).resolve()
        plot_dir.mkdir(parents=True, exist_ok=True)
        r_plot_dir = plot_dir.as_posix()
    else:
        r_plot_dir = ro.NULL

    with R_LOCK:
        with default_converter.context():
            result = ro.r["run_sar_analysis"](
                file_path.as_posix(),
                ro.IntVector([int(p) for p in positions]),
                str(signal_integral),
                str(background_integral),
                r_plot_dir,
            )

            signal_range = r_int_list(result.rx2("signal_integral"))
            background_range = r_int_list(result.rx2("background_integral"))

            n_requested = r_scalar_int(result.rx2("n_requested"))
            n_success = r_scalar_int(result.rx2("n_success"))
            n_failed = r_scalar_int(result.rx2("n_failed"))

            position_list = r_int_list(result.rx2("position"))
            de_list = r_float_list(result.rx2("de"))
            de_error_list = r_float_list(result.rx2("de_error"))
            rc_status_list = r_str_list(result.rx2("rc_status"))
            fit_list = r_str_list(result.rx2("fit"))
            n_n_list = r_float_list(result.rx2("n_n"))
            recycling_list = r_float_list(result.rx2("recycling_ratio"))
            recuperation_list = r_float_list(result.rx2("recuperation"))
            plot_file_list = r_str_list(result.rx2("plot_file"))

            qc_position_list = r_int_list(result.rx2("qc_position"))
            qc_criteria_list = r_str_list(result.rx2("qc_criteria"))
            qc_value_list = r_float_list(result.rx2("qc_value"))
            qc_threshold_list = r_float_list(result.rx2("qc_threshold"))
            qc_status_list = r_str_list(result.rx2("qc_status"))

            failed_position_list = r_int_list(result.rx2("failed_position"))
            failed_reason_list = r_str_list(result.rx2("failed_reason"))

    aliquots = [
        {
            "position": position_list[i],
            "de": de_list[i],
            "de_error": de_error_list[i],
            "rc_status": rc_status_list[i],
            "fit": fit_list[i],
            "n_n": n_n_list[i],
            "recycling_ratio": recycling_list[i],
            "recuperation": recuperation_list[i],
            "plot_file": plot_file_list[i] if i < len(plot_file_list) else None,
        }
        for i in range(len(position_list))
    ]

    qc_rows = [
        {
            "position": qc_position_list[i],
            "criteria": qc_criteria_list[i],
            "value": qc_value_list[i],
            "threshold": qc_threshold_list[i],
            "status": qc_status_list[i],
        }
        for i in range(len(qc_position_list))
    ]

    failed = [
        {
            "position": failed_position_list[i],
            "reason": failed_reason_list[i],
        }
        for i in range(len(failed_position_list))
    ]

    # QC 판정: RC.Status == "FAILED"면 품질 기준 미달.
    # 여기서 걸러 버리지 않고 분류만 해둔다. 실제로 De 분포에 무엇을 넣을지는
    # 다음 단계에서 연구자가 고르는 편이 이 프로젝트 취지에 맞다.
    accepted = [a for a in aliquots if str(a["rc_status"]).upper() != "FAILED"]
    rejected = [a for a in aliquots if str(a["rc_status"]).upper() == "FAILED"]

    return {
        "signal_integral": signal_range,
        "background_integral": background_range,
        "n_requested": n_requested,
        "n_success": n_success,
        "n_failed": n_failed,
        "n_accepted": len(accepted),
        "n_rejected": len(rejected),
        "aliquots": aliquots,
        "accepted": accepted,
        "rejected": rejected,
        "qc_rows": qc_rows,
        "failed": failed,
    }


# version4: De distribution analysis
def analyse_de_distribution(
    de: list[float],
    de_error: list[float],
    output_dir: str | Path | None = None,
    sigmab: float = 0.15,
    prefix: str = "de_dist",
) -> dict:
    """
    De 값 분포의 특성(과분산/왜도/첨도)을 계산하고, FMM 성분 수별 BIC 비교로
    다봉성 근거를 낸다. output_dir이 있으면 radial/abanico plot도 저장한다.

    R pipeline:
    - analyse_de_distribution(de, de_error, output_dir, prefix): 분포 지표 + plot
    - fit_finite_mixture(de, de_error, sigmab): 성분 수별 BIC (다봉성 판정용)

    통계는 여기까지가 R 몫이다. 이 지표를 CAM/MAM/FMM으로 매핑하는 결정 로직은
    model_recommend.recommend_age_model(순수 파이썬)이 담당하며, 호출부(탭)에서
    이 함수 결과를 그 함수에 넘긴다. r_runner는 R 브리지에 머문다.

    FMM 적합은 실패할 수 있다(유효 De < 4개, 수렴 실패 등). 그때는 분포 지표는
    그대로 두고 fmm=None, fmm_error에 사유를 담아 돌려준다 — 다봉성만 판정하지
    못할 뿐 CAM/MAM 판단은 지표만으로 가능하기 때문이다.

    Python return:
    - 분포 지표(dict) + sigmab + "fmm"(BIC 비교 dict 또는 None) + "fmm_error"
    """
    load_r_pipeline()

    if len(de) != len(de_error):
        raise ValueError(
            f"De 값과 오차의 개수가 다릅니다: {len(de)} vs {len(de_error)}"
        )

    if output_dir is not None:
        output_dir = Path(output_dir).resolve()
        output_dir.mkdir(parents=True, exist_ok=True)
        r_output_dir = output_dir.as_posix()
    else:
        r_output_dir = ro.NULL

    with R_LOCK:
        with default_converter.context():
            r_de = ro.FloatVector(
                [float("nan") if x is None else float(x) for x in de]
            )
            r_de_error = ro.FloatVector(
                [float("nan") if x is None else float(x) for x in de_error]
            )

            result = ro.r["analyse_de_distribution"](
                r_de,
                r_de_error,
                r_output_dir,
                str(prefix),
            )

            descriptors = {
                "n": r_scalar_int(result.rx2("n")),
                "n_dropped": r_scalar_int(result.rx2("n_dropped")),
                "central_de": r_scalar_float(result.rx2("central_de")),
                "central_de_error": r_scalar_float(result.rx2("central_de_error")),
                "od_abs": r_scalar_float(result.rx2("od_abs")),
                "od_abs_error": r_scalar_float(result.rx2("od_abs_error")),
                "od_rel": r_scalar_float(result.rx2("od_rel")),
                "od_rel_error": r_scalar_float(result.rx2("od_rel_error")),
                "skewness": r_scalar_float(result.rx2("skewness")),
                "skewness_weighted": r_scalar_float(result.rx2("skewness_weighted")),
                "kurtosis": r_scalar_float(result.rx2("kurtosis")),
                "mean_de": r_scalar_float(result.rx2("mean_de")),
                "median_de": r_scalar_float(result.rx2("median_de")),
                "sd_rel": r_scalar_float(result.rx2("sd_rel")),
                "radial_plot_file": r_scalar_str(result.rx2("radial_plot_file")),
                "abanico_plot_file": r_scalar_str(result.rx2("abanico_plot_file")),
            }

            # FMM은 실패할 수 있으므로 분포 지표와 분리해서 감싼다. 위 분포 지표는
            # 이미 파이썬 값으로 뽑혔으므로 FMM이 실패해도 영향받지 않는다.
            try:
                fmm_result = ro.r["fit_finite_mixture"](
                    r_de,
                    r_de_error,
                    float(sigmab),
                )

                fmm = {
                    "sigmab": r_scalar_float(fmm_result.rx2("sigmab")),
                    "single_bic": r_scalar_float(fmm_result.rx2("single_bic")),
                    "k": r_int_list(fmm_result.rx2("k")),
                    "bic": r_float_list(fmm_result.rx2("bic")),
                    "best_k": r_scalar_int(fmm_result.rx2("best_k")),
                    "best_bic": r_scalar_float(fmm_result.rx2("best_bic")),
                    "delta_bic": r_scalar_float(fmm_result.rx2("delta_bic")),
                }
                # 특이행렬/미수렴 시 calc_FiniteMixture는 예외 대신 NA BIC를 돌려주고,
                # 그러면 위 필드가 전부 None인 dict가 만들어진다. "fmm은 dict-or-None"
                # 불변식을 지키려 그런 경우를 None으로 접어 준다(추천 로직이 이걸 가정한다).
                if fmm["delta_bic"] is None or fmm["best_k"] is None:
                    fmm = None
                    fmm_error = "FMM 적합 결과가 유효하지 않습니다(특이행렬/미수렴 등)."
                else:
                    fmm_error = None
            except Exception as exc:
                fmm = None
                lines = str(exc).strip().splitlines()
                fmm_error = lines[-1].strip() if lines else "FMM 적합에 실패했습니다."

    return {
        **descriptors,
        "sigmab": float(sigmab),
        "fmm": fmm,
        "fmm_error": fmm_error,
    }


# ============================================================
# 셀프 체크
# ============================================================
# R 계층은 파이썬 쪽에서 R 벡터를 손으로 풀어 dict로 만들기 때문에,
# R 함수가 바뀌거나 Luminescence 버전이 오르면 조용히 모양이 어긋난다.
# 실제 분석을 한 번 통과시켜서 반환 모양과 값이 그대로인지 확인한다.
#
# 검증 데이터는 저장소에 없다(outputs/는 git에서 제외). Luminescence가
# 들고 있는 CWOSL.SAR.Data 예제를 그때그때 임시 폴더에 써서 쓴다.
#
# 실행: venv/bin/python app/utils/r_runner.py   (약 2초)

def _write_fixture(target_dir: Path) -> Path:
    """Luminescence 예제 데이터를 rda로 저장해 검증용 입력을 만든다."""
    import subprocess

    fixture = target_dir / "fixture.rda"

    script = (
        'suppressMessages(library(Luminescence)); '
        'data(ExampleData.BINfileData, envir=environment()); '
        f'save(CWOSL.SAR.Data, file="{fixture.as_posix()}")'
    )

    done = subprocess.run(
        ["Rscript", "-e", script],
        capture_output=True,
        text=True,
    )

    if done.returncode != 0 or not fixture.exists():
        raise RuntimeError(f"검증용 fixture 생성 실패: {done.stderr.strip()}")

    return fixture


if __name__ == "__main__":
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        fixture = _write_fixture(tmp_dir)

        # --------------------------------------------------------
        # 1. 파일 검사
        # --------------------------------------------------------
        info = inspect_uploaded_file(fixture)

        assert info["positions"] == list(range(1, 25)), \
            f"POSITION 목록이 달라졌다: {info['positions']}"
        assert info["n_positions"] == 24, f"POSITION 수: {info['n_positions']}"
        assert info["object_name"] == "CWOSL.SAR.Data", \
            f"rda에서 고른 객체 이름: {info['object_name']}"
        assert info["n_candidates"] == 1, "후보 객체가 하나여야 한다"

        # --------------------------------------------------------
        # 2. record 검사 — 모든 컬럼의 길이가 같아야 한다.
        #    하나라도 어긋나면 build_record_rows가 조용히 잘린 표를 만든다.
        # --------------------------------------------------------
        recs = inspect_rlum_records(fixture, 1)

        n = len(recs["record_index"])
        assert n == 30, f"POSITION 1의 record 수: {n}"

        for key in ("record_type", "dtype", "comment", "run", "set",
                    "irr_time", "npoints", "low", "high",
                    "an_temp", "an_time", "light_source"):
            assert len(recs[key]) == n, f"'{key}' 길이가 record_index와 다르다"

        assert {"OSL", "IRSL", "TL"} <= set(recs["record_type"]), \
            f"기대한 curve type이 없다: {set(recs['record_type'])}"

        # --------------------------------------------------------
        # 3. 곡선 PNG — macOS quartz는 dev.off() 시점에야 파일을 쓴다.
        #    이 순서가 틀어지면 예외 없이 빈 파일만 남으므로, 경로가
        #    아니라 "디스크에 실제로 있고 비어 있지 않은지"를 본다.
        # --------------------------------------------------------
        osl_index = next(
            idx for idx, kind in zip(recs["record_index"], recs["record_type"])
            if kind == "OSL"
        )

        plot = generate_rlum_record_plot(fixture, tmp_dir, 1, osl_index)
        plot_file = Path(plot["plot_file"])

        assert plot_file.exists(), f"곡선 PNG가 생성되지 않았다: {plot_file}"
        assert plot_file.stat().st_size > 0, "곡선 PNG가 비어 있다"

        # --------------------------------------------------------
        # 4. SAR 분석
        # --------------------------------------------------------
        sar_dir = tmp_dir / "sar"
        sar_dir.mkdir()

        sar = run_sar_analysis(fixture, [1, 2], "1:2", "900:1000", sar_dir)

        # analyse_SAR.CWOSL()은 min/max가 아니라 벡터를 받는다.
        # 이 형태가 깨지면 De가 통째로 달라지므로 왕복해서 확인한다.
        assert sar["signal_integral"] == [1, 2], \
            f"signal_integral: {sar['signal_integral']}"
        assert sar["background_integral"] == [900, 1000], \
            f"background_integral: {sar['background_integral']}"

        # 배치는 실패를 모아서 돌려준다. 요청한 수와 성공+실패가 맞아야
        # 한 aliquot이 조용히 사라지지 않는다.
        assert sar["n_requested"] == 2, f"n_requested: {sar['n_requested']}"
        assert sar["n_success"] + sar["n_failed"] == sar["n_requested"], \
            "요청 수와 성공+실패 수가 맞지 않는다"
        assert len(sar["aliquots"]) == sar["n_success"], \
            "aliquot 수와 n_success가 맞지 않는다"
        assert len(sar["accepted"]) + len(sar["rejected"]) == len(sar["aliquots"]), \
            "accepted + rejected가 전체 aliquot과 맞지 않는다"

        assert sar["qc_rows"], "QC 표가 비어 있다"
        assert {"criteria", "position", "status", "threshold", "value"} \
            <= set(sar["qc_rows"][0]), f"QC 컬럼이 달라졌다: {sar['qc_rows'][0].keys()}"

        # --------------------------------------------------------
        # 5. De 값
        #    아래 범위는 Luminescence 1.2.1에서 실측한 값 기준이다
        #    (POSITION 1: 1661.3 Gy / POSITION 2: 1534.9 Gy).
        #    여기서 벗어나면 Luminescence를 올렸거나 계산이 바뀐 것이다.
        #    어느 쪽인지는 연대값에 직접 영향을 주므로 사람이 판단해야 한다.
        # --------------------------------------------------------
        expected_de = {1: (1600, 1720), 2: (1480, 1590)}

        for aliquot in sar["aliquots"]:
            pos = aliquot["position"]
            de = aliquot["de"]

            assert isinstance(de, float) and de == de, \
                f"POSITION {pos}의 De가 수치가 아니다: {de}"

            low, high = expected_de[pos]
            assert low < de < high, \
                f"POSITION {pos}의 De가 실측 범위를 벗어났다: {de:.1f} (기대 {low}~{high})"

            assert aliquot["rc_status"], f"POSITION {pos}에 QC 판정이 없다"

            # 성장곡선 PNG도 실제로 쓰였는지 본다 (3번과 같은 이유)
            dose_plot = Path(aliquot["plot_file"])
            assert dose_plot.exists() and dose_plot.stat().st_size > 0, \
                f"POSITION {pos}의 성장곡선 PNG가 없거나 비어 있다"

        # --------------------------------------------------------
        # 6. 입력 검증은 R에서 막고 파이썬까지 예외로 올라와야 한다.
        #    조용히 빈 결과를 돌려주면 UI가 "분석 성공"으로 표시한다.
        # --------------------------------------------------------
        for bad_input, label in (
            (tmp_dir / "없는파일.rda", "없는 경로"),
            (tmp_dir / "fixture.txt", "지원하지 않는 확장자"),
        ):
            if label == "지원하지 않는 확장자":
                bad_input.write_text("not a bin file")

            try:
                inspect_uploaded_file(bad_input)
                raise AssertionError(f"{label}인데 예외가 나지 않았다")
            except AssertionError:
                raise
            except Exception:
                pass

        try:
            run_sar_analysis(fixture, [1, 99], "1:2", "900:1000", sar_dir)
            raise AssertionError("파일에 없는 POSITION인데 예외가 나지 않았다")
        except AssertionError:
            raise
        except Exception:
            pass

        # --------------------------------------------------------
        # 7. De 분포 분석 + FMM + 추천 (Phase A)
        #    ExampleData.DeValues의 검증된 분포로 지표/추천이 그대로인지 본다.
        #    CA1(n=62):  과분산 34.7%, 대칭, 다봉(ΔBIC 95.5) -> FMM
        #    BT998(n=25): 과분산 8.0% -> OD 게이트에서 CAM
        #    이 값들이 흔들리면 Luminescence가 올랐거나 계산이 바뀐 것이다.
        # --------------------------------------------------------
        de_dir = tmp_dir / "de"
        de_dir.mkdir()

        # De 벡터를 R에서 가져온다. 이 with 블록을 빠져나온 뒤에
        # analyse_de_distribution을 부른다 (Lock은 재진입 불가라 중첩 금지).
        with R_LOCK:
            with default_converter.context():
                ro.r('data("ExampleData.DeValues")')
                ca1_de = r_float_list(ro.r("ExampleData.DeValues$CA1[[1]]"))
                ca1_err = r_float_list(ro.r("ExampleData.DeValues$CA1[[2]]"))
                bt_de = r_float_list(ro.r("ExampleData.DeValues$BT998[[1]]"))
                bt_err = r_float_list(ro.r("ExampleData.DeValues$BT998[[2]]"))

        ca1 = analyse_de_distribution(ca1_de, ca1_err, output_dir=de_dir,
                                      sigmab=0.15, prefix="ca1")

        assert ca1["n"] == 62, f"CA1 n: {ca1['n']}"
        assert 33 < ca1["od_rel"] < 36, \
            f"CA1 과분산이 실측 범위를 벗어났다: {ca1['od_rel']}"
        assert -0.2 < ca1["skewness"] < 0.2, f"CA1 왜도: {ca1['skewness']}"
        assert ca1["fmm"] is not None and ca1["fmm_error"] is None, \
            f"CA1 FMM 적합이 실패했다: {ca1['fmm_error']}"
        assert ca1["fmm"]["delta_bic"] > 6, \
            f"CA1 다봉 근거(ΔBIC)가 약하다: {ca1['fmm']['delta_bic']}"

        # radial/abanico PNG가 실제로 디스크에 쓰였는지 (macOS quartz와 같은 이유)
        for key in ("radial_plot_file", "abanico_plot_file"):
            f = Path(ca1[key])
            assert f.exists() and f.stat().st_size > 0, \
                f"CA1 {key} PNG가 없거나 비어 있다"

        # 결정 로직까지 이은 전체 사슬. self-check는 app/utils 컨텍스트에서 돌아가므로
        # model_recommend를 직접 import 한다 (운영 코드는 r_runner가 이걸 import 하지 않는다).
        from model_recommend import recommend_age_model

        rec_ca1 = recommend_age_model(ca1["od_rel"], ca1["skewness"], ca1["n"], ca1["fmm"])
        assert rec_ca1["model"] == "FMM", f"CA1 추천이 FMM이 아니다: {rec_ca1['model']}"

        # BT998: OD 게이트에서 CAM. plot 없이 지표만 뽑는 경로도 함께 확인.
        bt = analyse_de_distribution(bt_de, bt_err, sigmab=0.15)
        assert bt["n"] == 25, f"BT998 n: {bt['n']}"
        assert 7 < bt["od_rel"] < 9, f"BT998 과분산: {bt['od_rel']}"
        assert bt["radial_plot_file"] is None, \
            "output_dir을 안 줬는데 plot 경로가 생겼다"

        rec_bt = recommend_age_model(bt["od_rel"], bt["skewness"], bt["n"], bt["fmm"])
        assert rec_bt["model"] == "CAM", f"BT998 추천이 CAM이 아니다: {rec_bt['model']}"

        # 유효 De가 3개 미만이면 R에서 막고 예외가 파이썬까지 올라와야 한다.
        try:
            analyse_de_distribution([100.0, 200.0], [10.0, 20.0])
            raise AssertionError("De가 2개인데 예외가 나지 않았다")
        except AssertionError:
            raise
        except Exception:
            pass

    print("r_runner self-check OK")
