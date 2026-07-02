# app/utils/file_utils.py

from pathlib import Path
import re
import shutil


# ============================================================
# 1. 안전한 파일/폴더 이름 만들기
# ============================================================
def sanitize_name(name: str) -> str:
    """
    파일명이나 sample_id에 쓰기 안전한 이름으로 바꾼다.

    예:
        "CWOSL SAR example.rda"
        -> "CWOSL_SAR_example"

    이유:
        파일명에 공백, 괄호, 특수문자가 많으면
        나중에 R/Python/경로 처리에서 귀찮아질 수 있음.
    """

    # 확장자 제거
    stem = Path(name).stem

    # 영문, 숫자, 한글, 언더스코어, 하이픈만 남기고 나머지는 _
    safe = re.sub(r"[^0-9a-zA-Z가-힣_-]+", "_", stem)

    # 언더스코어가 여러 개 연속되면 하나로 줄임
    safe = re.sub(r"_+", "_", safe)

    # 앞뒤 언더스코어 제거
    safe = safe.strip("_")

    # 혹시 이름이 비면 기본값 사용
    return safe or "sample"


# ============================================================
# 2. 중복되지 않는 sample_id 만들기
# ============================================================
def make_unique_sample_id(base_name: str, samples_dir: Path) -> str:
    """
    outputs/samples 안에서 중복되지 않는 sample_id를 만든다.

    예:
        CWOSL_SAR_example
        CWOSL_SAR_example_2
        CWOSL_SAR_example_3
    """

    base_id = sanitize_name(base_name)

    sample_id = base_id
    index = 2

    while (samples_dir / sample_id).exists():
        sample_id = f"{base_id}_{index}"
        index += 1

    return sample_id


# ============================================================
# 3. sample 폴더 구조 생성
# ============================================================
def create_sample_dirs(samples_dir: Path, sample_id: str) -> dict:
    """
    하나의 sample에 필요한 폴더들을 만든다.

    실제 저장 구조:
        outputs/samples/{sample_id}/
          raw/
          inspect/
          curve_plot/
          analysis_results/

    지금 1단계에서는 raw, inspect만 쓰지만
    뒤 단계에서 쓸 폴더도 미리 만들어둔다.
    """

    sample_dir = samples_dir / sample_id

    paths = {
        "sample_dir": sample_dir,
        "raw_dir": sample_dir / "raw",
        "inspect_dir": sample_dir / "inspect",
        "curve_plot_dir": sample_dir / "curve_plot",
        "analysis_results_dir": sample_dir / "analysis_results",
    }

    for path in paths.values():
        path.mkdir(parents=True, exist_ok=True)

    return paths


# ============================================================
# 4. 업로드 파일 저장
# ============================================================
def save_uploaded_file(uploaded_file, samples_dir: Path) -> dict:
    """
    Streamlit에서 업로드된 BIN/RDA 파일을 sample 폴더에 저장한다.

    입력:
        uploaded_file:
            st.file_uploader()가 반환한 파일 객체

        samples_dir:
            outputs/samples 경로

    출력:
        {
            "sample_id": "...",
            "sample_dir": Path(...),
            "raw_path": Path(...)
        }
    """

    samples_dir.mkdir(parents=True, exist_ok=True)

    # 업로드 파일명을 기준으로 sample_id 생성
    sample_id = make_unique_sample_id(uploaded_file.name, samples_dir)

    # sample 폴더 구조 생성
    paths = create_sample_dirs(samples_dir, sample_id)

    # 원본 확장자는 유지
    suffix = Path(uploaded_file.name).suffix
    raw_path = paths["raw_dir"] / f"{sample_id}{suffix}"

    # BIN/RDA는 binary 파일이므로 wb로 저장
    with open(raw_path, "wb") as f:
        f.write(uploaded_file.getbuffer())

    return {
        "sample_id": sample_id,
        "sample_dir": paths["sample_dir"],
        "raw_path": raw_path,
        "paths": paths,
    }


# ============================================================
# 5. 기존 sample 폴더 목록 읽기
# ============================================================
def list_samples(samples_dir: Path) -> list[dict]:
    """
    outputs/samples 안에 있는 sample 폴더 목록을 읽는다.

    나중에 앱을 껐다 켜도 왼쪽 Research Workspace를 복원하려면
    이 함수가 필요해짐.

    지금 1단계에서는 필수는 아니지만,
    구조상 넣어두면 다음 단계에서 바로 쓸 수 있음.
    """

    if not samples_dir.exists():
        return []

    samples = []

    for sample_dir in sorted(samples_dir.iterdir()):
        if not sample_dir.is_dir():
            continue

        raw_dir = sample_dir / "raw"
        raw_files = list(raw_dir.glob("*")) if raw_dir.exists() else []

        samples.append(
            {
                "sample_id": sample_dir.name,
                "sample_dir": sample_dir,
                "raw_files": raw_files,
            }
        )

    return samples


# ============================================================
# 6. sample 삭제
# ============================================================
def delete_sample(sample_dir: Path) -> None:
    """
    sample 폴더 전체를 삭제한다.

    주의:
        나중에 UI에서 삭제 버튼을 만들 때만 사용.
        지금 1단계에서는 굳이 호출하지 않아도 됨.
    """

    if sample_dir.exists() and sample_dir.is_dir():
        shutil.rmtree(sample_dir)