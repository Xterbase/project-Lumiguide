# app/utils/file_utils.py

from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import shutil


# ============================================================
# 0. sample 폴더 규약
# ============================================================
# 폴더명: {샘플명}_{YYYYMMDD}_{NN}
#   예) ExampleData_20260714_01
#
# 같은 시료의 측정들이 이름순으로 한데 모이고,
# 그 안에서 날짜/번호로 언제 올린 것인지 구분된다.
#
# 각 sample 폴더에는 sample.json(메타)을 함께 남긴다.
# 이게 있어야 "이미 올린 파일인지"를 내용 해시로 판단해서
# 같은 파일을 다시 올릴 때 폴더가 중복 생성되는 걸 막을 수 있다.

SAMPLE_META_FILE = "sample.json"

# 폴더명이 너무 길면 macOS 파일명 길이 제한(255바이트)에 걸려 mkdir/open이 터진다.
# 날짜(8) + 번호(2) + 구분자까지 붙는 걸 감안해 stem을 넉넉히 잘라둔다.
MAX_STEM_LENGTH = 80


# ============================================================
# 0-1. 업로드 파일 내용 해시
# ============================================================
def compute_upload_hash(uploaded_file) -> str:
    """
    업로드된 파일의 내용을 sha256으로 해시한다.

    이유:
        파일명만으로 "같은 파일"인지 판단하면,
        이름이 같고 내용이 다른 파일(예: 재측정한 data.bin)을 올렸을 때
        이전 파일 기준 결과가 그대로 남아 조용히 틀린 분석이 나온다.
        내용 해시로 비교해야 이 오판을 막을 수 있다.
    """
    return hashlib.sha256(uploaded_file.getbuffer()).hexdigest()


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

    # 길이 제한 (파일명 길이 제한으로 mkdir/open이 터지는 걸 방지)
    safe = safe[:MAX_STEM_LENGTH].strip("_")

    # 혹시 이름이 비면 기본값 사용
    return safe or "sample"


# ============================================================
# 2. sample_id 만들기: {샘플명}_{YYYYMMDD}_{NN}
# ============================================================
def make_sample_id(
    base_name: str,
    samples_dir: Path,
    today: str | None = None,
) -> str:
    """
    outputs/samples 안에서 중복되지 않는 sample_id를 만든다.

    예:
        ExampleData_20260714_01
        ExampleData_20260714_02   (같은 날 다시 올린 다른 파일)
        ExampleData_20260715_01   (다음 날)

    번호(NN)는 "같은 샘플명 + 같은 날짜"를 쓰는 기존 폴더가 몇 개인지 보고 이어붙인다.
    """

    stem = sanitize_name(base_name)
    today = today or datetime.now().strftime("%Y%m%d")

    prefix = f"{stem}_{today}_"

    index = 1

    while (samples_dir / f"{prefix}{index:02d}").exists():
        index += 1

    return f"{prefix}{index:02d}"


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
# 4. sample 메타(sample.json) 읽기/쓰기
# ============================================================
# sample.json에는 경로가 아니라 "파일 이름"만 적는다.
# 프로젝트 폴더를 옮기거나 이름을 바꿔도 sample 폴더 기준으로 경로를 다시 만들 수 있게 하기 위함이다.

def _write_sample_meta(
    sample_dir: Path,
    sample_id: str,
    file_hash: str,
    original_file_name: str,
    raw_file_name: str,
) -> None:
    meta = {
        "sample_id": sample_id,
        "file_hash": file_hash,
        "original_file_name": original_file_name,
        "raw_file_name": raw_file_name,
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }

    (sample_dir / SAMPLE_META_FILE).write_text(
        json.dumps(meta, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _read_sample_meta(sample_dir: Path) -> dict | None:
    meta_path = sample_dir / SAMPLE_META_FILE

    if not meta_path.exists():
        return None

    try:
        return json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        # 메타가 깨졌으면 "없는 것"으로 취급한다 (새로 저장하면 복구된다)
        return None


def _build_sample(sample_id: str, paths: dict, raw_path: Path, file_hash: str) -> dict:
    return {
        "sample_id": sample_id,
        "sample_dir": paths["sample_dir"],
        "raw_path": raw_path,
        "paths": paths,
        "file_hash": file_hash,
    }


def find_sample_by_hash(samples_dir: Path, file_hash: str) -> dict | None:
    """
    이미 저장된 sample 중 내용 해시가 같은 것을 찾는다.

    같은 파일을 다시 업로드했을 때 폴더를 새로 만들지 않고 기존 것을 재사용하기 위함이다.
    (전에는 재업로드마다 ExampleData_2, _3, _4 ... 로 원본 사본이 계속 쌓였다)
    """

    if not samples_dir.exists():
        return None

    for sample_dir in sorted(samples_dir.iterdir()):
        if not sample_dir.is_dir():
            continue

        meta = _read_sample_meta(sample_dir)

        if meta is None or meta.get("file_hash") != file_hash:
            continue

        raw_path = sample_dir / "raw" / str(meta.get("raw_file_name", ""))

        # 메타는 남아 있는데 원본이 지워진 경우 → 재사용하지 않고 새로 저장하게 둔다
        if not raw_path.exists():
            continue

        paths = create_sample_dirs(samples_dir, sample_dir.name)

        return _build_sample(
            sample_id=sample_dir.name,
            paths=paths,
            raw_path=raw_path,
            file_hash=file_hash,
        )

    return None


# ============================================================
# 5. 업로드 파일 저장
# ============================================================
def save_uploaded_file(
    uploaded_file,
    samples_dir: Path,
    file_hash: str | None = None,
) -> dict:
    """
    Streamlit에서 업로드된 BIN/RDA 파일을 sample 폴더에 저장한다.

    내용 해시가 같은 sample이 이미 있으면 저장하지 않고 그 폴더를 재사용한다.
    (이전 분석 결과 curve_plot/ 등도 그대로 남는다)

    출력:
        {
            "sample_id": "ExampleData_20260714_01",
            "sample_dir": Path(...),
            "raw_path": Path(...),
            "paths": {...},
            "file_hash": "...",
            "reused": bool,     # 기존 폴더를 재사용했는지
        }
    """

    samples_dir.mkdir(parents=True, exist_ok=True)

    if file_hash is None:
        file_hash = compute_upload_hash(uploaded_file)

    # ------------------------------------------------------------
    # 이미 올린 적 있는 파일이면 기존 폴더 재사용
    # ------------------------------------------------------------
    existing = find_sample_by_hash(samples_dir, file_hash)

    if existing is not None:
        return {**existing, "reused": True}

    # ------------------------------------------------------------
    # 새 파일 → {샘플명}_{YYYYMMDD}_{NN} 폴더 생성
    # ------------------------------------------------------------
    sample_id = make_sample_id(uploaded_file.name, samples_dir)
    paths = create_sample_dirs(samples_dir, sample_id)

    # 원본 확장자는 유지
    suffix = Path(uploaded_file.name).suffix
    raw_file_name = f"{sample_id}{suffix}"
    raw_path = paths["raw_dir"] / raw_file_name

    # BIN/RDA는 binary 파일이므로 wb로 저장
    with open(raw_path, "wb") as f:
        f.write(uploaded_file.getbuffer())

    _write_sample_meta(
        sample_dir=paths["sample_dir"],
        sample_id=sample_id,
        file_hash=file_hash,
        original_file_name=uploaded_file.name,
        raw_file_name=raw_file_name,
    )

    return {
        **_build_sample(sample_id, paths, raw_path, file_hash),
        "reused": False,
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
def save_sar_results(analysis_results_dir: Path, result: dict) -> dict:
    """
    SAR 결과를 CSV로 저장한다.

    결과가 세션 메모리에만 있으면 앱을 껐다 켤 때마다 재분석해야 하고,
    다음 단계(De 분포)나 외부 도구로 넘길 수도 없다.
    De 값은 연구 산출물이므로 디스크에 남긴다.

    저장 파일:
        sar_de_table.csv        전체 aliquot의 De/오차/품질
        sar_qc_table.csv        POSITION별 rejection criteria 전 항목
        sar_accepted_de.csv     RC.Status가 FAILED가 아닌 것
        sar_rejected_de.csv     FAILED인 것
        sar_failed_positions.csv  분석 자체가 실패한 POSITION과 사유

    반환: {이름: 저장 경로} — 실제로 저장한 것만 담는다.
    """

    import pandas as pd

    analysis_results_dir = Path(analysis_results_dir)
    analysis_results_dir.mkdir(parents=True, exist_ok=True)

    tables = {
        "de_table": (result.get("aliquots"), "sar_de_table.csv"),
        "qc_table": (result.get("qc_rows"), "sar_qc_table.csv"),
        "accepted": (result.get("accepted"), "sar_accepted_de.csv"),
        "rejected": (result.get("rejected"), "sar_rejected_de.csv"),
        "failed": (result.get("failed"), "sar_failed_positions.csv"),
    }

    saved = {}

    for name, (rows, file_name) in tables.items():
        # 빈 표는 만들지 않는다. 빈 CSV가 남아 있으면 이전 분석 결과인지
        # 이번에 아무것도 안 나온 것인지 구분되지 않는다.
        if not rows:
            continue

        file_path = analysis_results_dir / file_name
        pd.DataFrame(rows).to_csv(file_path, index=False, encoding="utf-8-sig")
        saved[name] = file_path

    return saved


def delete_sample(sample_dir: Path) -> None:
    """
    sample 폴더 전체를 삭제한다.

    주의:
        나중에 UI에서 삭제 버튼을 만들 때만 사용.
        지금 1단계에서는 굳이 호출하지 않아도 됨.
    """

    if sample_dir.exists() and sample_dir.is_dir():
        shutil.rmtree(sample_dir)