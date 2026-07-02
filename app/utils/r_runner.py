from pathlib import Path
from threading import Lock

import rpy2.robjects as ro
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
def r_vector_to_list(r_vector):
    """
    R vector를 Python list로 변환한다.
    """
    if r_vector is None:
        return []

    return list(r_vector)

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

            file_name = str(result.rx2("file")[0])
            file_path_result = str(result.rx2("file_path")[0])
            file_type = str(result.rx2("file_type")[0])
            object_name = str(result.rx2("object_name")[0])

            n_metadata_rows = int(result.rx2("n_metadata_rows")[0])
            metadata_columns = [
                str(x) for x in r_vector_to_list(result.rx2("metadata_columns"))
            ]

            n_positions = int(result.rx2("n_positions")[0])
            positions = [
                int(x) for x in r_vector_to_list(result.rx2("positions"))
            ]

            record_types = [
                str(x) for x in r_vector_to_list(result.rx2("record_types"))
            ]

    return {
        "file": file_name,
        "file_path": file_path_result,
        "file_type": file_type,
        "object_name": object_name,
        "n_metadata_rows": n_metadata_rows,
        "metadata_columns": metadata_columns,
        "n_positions": n_positions,
        "positions": positions,
        "record_types": record_types,
    }