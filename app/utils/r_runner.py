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

    with R_LOCK:
        with default_converter.context():
            result = ro.r["run_sar_analysis"](
                file_path.as_posix(),
                ro.IntVector([int(p) for p in positions]),
                str(signal_integral),
                str(background_integral),
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
        }
        for i in range(len(position_list))
    ]

    failed = [
        {
            "position": failed_position_list[i],
            "reason": failed_reason_list[i],
        }
        for i in range(len(failed_position_list))
    ]

    return {
        "signal_integral": signal_range,
        "background_integral": background_range,
        "n_requested": n_requested,
        "n_success": n_success,
        "n_failed": n_failed,
        "aliquots": aliquots,
        "failed": failed,
    }