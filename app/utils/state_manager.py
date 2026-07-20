# app/utils/state_manager.py

from __future__ import annotations

import streamlit as st


# ============================================================
# 0. session_state key 상수
# ============================================================
# 문자열 오타 방지 + 호출부 가독성을 위해 상수로 관리한다.

UPLOADED_SAMPLE_KEY = "uploaded_sample"
UPLOADED_FILE_NAME_KEY = "uploaded_file_name"
UPLOADED_FILE_HASH_KEY = "uploaded_file_hash"
POSITION_RESULT_KEY = "position_result"
SELECTED_SIGNAL_POSITION_KEY = "selected_signal_position"
RLUM_RECORDS_KEY = "rlum_records"
SELECTED_RECORD_INFO_KEY = "selected_record_info"
RLUM_RECORD_PLOT_RESULT_KEY = "rlum_record_plot_result"
SIGNAL_PARAMS_KEY = "signal_params"
SAR_TARGET_POSITIONS_KEY = "sar_target_positions"
SAR_RESULT_KEY = "sar_result"



# ============================================================
# 1. 단계(stage) 스키마 = 단일 진실 공급원
# ============================================================
# 각 stage 안에서 input / output을 구분한다.
#   - input  : 사용자/위젯이 직접 준 값 (업로드 파일, 선택한 position, 파라미터 등)
#   - output : 그 input으로 우리가 계산한 결과 (position 검사, RLum 레코드, SAR 결과 등)
#
# 이 구분이 핵심이다.
#   "어떤 stage의 input이 바뀌면 → 그 stage의 output + 이후 stage 전체가 무효"
# 라는 규칙 하나로 모든 reset이 자동으로 파생되기 때문에,
# 새 결과 키를 추가해도 reset 로직은 건드릴 필요가 없다.
#
# dict는 삽입 순서를 보존하므로, 여기 정의된 순서가 곧 파이프라인 순서다.

SESSION_SCHEMA: dict[str, dict[str, dict]] = {
    "upload": {
        "input": {
            UPLOADED_SAMPLE_KEY: None,
            UPLOADED_FILE_NAME_KEY: None,
            UPLOADED_FILE_HASH_KEY: None,
        },
        "output": {
            POSITION_RESULT_KEY: None,
        },
    },
    "signal": {
        "input": {
            SELECTED_SIGNAL_POSITION_KEY: None,
        },
        "output": {
            RLUM_RECORDS_KEY: None,
        },
    },
    "record": {
        "input": {
            SELECTED_RECORD_INFO_KEY: None,
        },
        "output": {
            RLUM_RECORD_PLOT_RESULT_KEY: None,
        },
    },
    "sar_setup": {
        "input": {
            SIGNAL_PARAMS_KEY: None,
        },
        "output": {},
    },
    "sar": {
        "input": {
            SAR_TARGET_POSITIONS_KEY: None,
        },
        "output": {
            SAR_RESULT_KEY: None,
        },
    },
}
# 파이프라인 순서 (스키마 정의 순서에서 파생 — 따로 손으로 관리하지 않는다)
STAGE_ORDER: list[str] = list(SESSION_SCHEMA.keys())


# ============================================================
# 2. 스키마 파생 헬퍼 (내부용)
# ============================================================

def _stage_input(stage: str) -> dict:
    return SESSION_SCHEMA[stage]["input"]


def _stage_output(stage: str) -> dict:
    return SESSION_SCHEMA[stage]["output"]


def _stage_all(stage: str) -> dict:
    """한 stage의 input + output 기본값을 합쳐서 반환한다."""
    return {**_stage_input(stage), **_stage_output(stage)}


def _all_defaults() -> dict:
    """이 모듈이 소유한 모든 key의 기본값 (평면)."""
    merged: dict = {}
    for stage in STAGE_ORDER:
        merged.update(_stage_all(stage))
    return merged


def _reset_keys(defaults: dict) -> None:
    """주어진 {key: default} 묶음을 기본값으로 되돌린다."""
    for key, default_value in defaults.items():
        st.session_state[key] = default_value


# ============================================================
# 3. 제네릭 접근자
# ============================================================
# 키 종류가 늘어도 함수는 이 3개 그대로다.
# 호출부: set_value(POSITION_RESULT_KEY, result) 형태.

def set_value(key: str, value) -> None:
    st.session_state[key] = value


def get_value(key: str):
    return st.session_state.get(key)


def has_value(key: str) -> bool:
    return get_value(key) is not None


# ============================================================
# 4. 초기화
# ============================================================

def init_session_state() -> None:
    """
    스키마에 정의된 모든 key를 기본값으로 초기화한다.

    setdefault를 쓰므로 이미 값이 있는 key는 덮어쓰지 않는다.
    따라서 rerun 되어도 기존 상태가 유지된다.

    중첩 스키마는 '조직/메타데이터'일 뿐, session_state에는 평면으로 펼친다.
    (위젯 key= 연동, mutation 추적이 평면 키에서 가장 안전하기 때문)
    """
    for key, default_value in _all_defaults().items():
        st.session_state.setdefault(key, default_value)


# ============================================================
# 5. 단계 기반 무효화 (핵심)
# ============================================================

def invalidate_from(stage: str) -> None:
    """
    어떤 stage의 input이 바뀌었을 때 호출한다.

    규칙:
      - 해당 stage의 output을 비운다 (방금 새로 준 input은 유지)
      - 이후 모든 stage를 input/output 통째로 비운다

    예) 새 파일 업로드 → invalidate_from("upload")
        → position_result(upload output) + signal 전체 + sar 전체가 비워진다.
        → uploaded_sample/uploaded_file_name(방금 set한 새 input)은 유지된다.

    새 stage나 새 결과 key를 추가해도 이 함수는 수정할 필요가 없다.
    """
    idx = STAGE_ORDER.index(stage)

    # 현재 stage: output만 비운다 (input은 방금 갱신했으므로 보존)
    _reset_keys(_stage_output(stage))

    # 이후 stage: input + output 전부 비운다
    for downstream in STAGE_ORDER[idx + 1:]:
        _reset_keys(_stage_all(downstream))


def reset_stage(stage: str) -> None:
    """특정 stage 하나만 input/output 통째로 비운다."""
    _reset_keys(_stage_all(stage))


# ============================================================
# 6. Upload 단계 wrapper
# ============================================================
# 위젯/호출부와 자주 엮이는 upload 단계는 의미가 드러나는 얇은 wrapper를 둔다.
# (내부는 제네릭 접근자 + invalidate_from을 재사용)

def set_current_sample(
    sample: dict,
    uploaded_file_name: str,
    file_hash: str,
) -> None:
    """
    현재 업로드된 sample 정보를 저장하고,
    이전 파일 기준으로 계산된 모든 다운스트림 결과를 무효화한다.
    """
    set_value(UPLOADED_SAMPLE_KEY, sample)
    set_value(UPLOADED_FILE_NAME_KEY, uploaded_file_name)
    set_value(UPLOADED_FILE_HASH_KEY, file_hash)
    invalidate_from("upload")


def get_current_sample() -> dict | None:
    return get_value(UPLOADED_SAMPLE_KEY)


def has_current_sample() -> bool:
    return has_value(UPLOADED_SAMPLE_KEY)


def get_uploaded_file_name() -> str | None:
    return get_value(UPLOADED_FILE_NAME_KEY)


def get_uploaded_file_hash() -> str | None:
    return get_value(UPLOADED_FILE_HASH_KEY)


def is_new_uploaded_file(uploaded_file_name: str, file_hash: str) -> bool:
    """
    현재 업로드된 파일이 기존 파일과 다른지 확인한다.

    내용 해시로 판단한다. 파일명만 비교하면 이름이 같고 내용이 다른 파일
    (재측정한 data.bin 등)을 "같은 파일"로 오판해서, 이전 파일 기준 결과가
    그대로 남은 채 조용히 틀린 분석이 나온다.

    파일명도 함께 비교하는 이유:
        내용이 같고 이름만 다른 파일을 올렸을 때도 UI 상태를 새로 잡아주기 위함이다.
        (디스크 저장은 별개다. file_utils는 해시가 같으면 기존 sample 폴더를
         재사용하므로, 이 경우 폴더가 새로 생기지는 않는다.)
    """
    return (
        get_value(UPLOADED_SAMPLE_KEY) is None
        or get_value(UPLOADED_FILE_HASH_KEY) != file_hash
        or get_value(UPLOADED_FILE_NAME_KEY) != uploaded_file_name
    )


# ============================================================
# 7. POSITION 결과 wrapper (선택적 편의 함수)
# ============================================================

def set_position_result(result: dict) -> None:
    set_value(POSITION_RESULT_KEY, result)


def get_position_result() -> dict | None:
    return get_value(POSITION_RESULT_KEY)


def has_position_result() -> bool:
    return has_value(POSITION_RESULT_KEY)

# ============================================================
# 8. Signal Analysis 단계 wrapper
# ============================================================

def set_selected_signal_position(position: int) -> None:
    set_value(SELECTED_SIGNAL_POSITION_KEY, position)


def get_selected_signal_position() -> int | None:
    return get_value(SELECTED_SIGNAL_POSITION_KEY)


def has_selected_signal_position() -> bool:
    return has_value(SELECTED_SIGNAL_POSITION_KEY)


def set_rlum_records(records: dict) -> None:
    set_value(RLUM_RECORDS_KEY, records)


def get_rlum_records() -> dict | None:
    return get_value(RLUM_RECORDS_KEY)


def has_rlum_records() -> bool:
    return has_value(RLUM_RECORDS_KEY)


def set_selected_record_info(record_info: dict) -> None:
    set_value(SELECTED_RECORD_INFO_KEY, record_info)


def get_selected_record_info() -> dict | None:
    return get_value(SELECTED_RECORD_INFO_KEY)


def has_selected_record_info() -> bool:
    return has_value(SELECTED_RECORD_INFO_KEY)


def set_rlum_record_plot_result(result: dict) -> None:
    set_value(RLUM_RECORD_PLOT_RESULT_KEY, result)


def get_rlum_record_plot_result() -> dict | None:
    return get_value(RLUM_RECORD_PLOT_RESULT_KEY)


def has_rlum_record_plot_result() -> bool:
    return has_value(RLUM_RECORD_PLOT_RESULT_KEY)


def set_signal_params(params: dict) -> None:
    set_value(SIGNAL_PARAMS_KEY, params)


def get_signal_params() -> dict | None:
    return get_value(SIGNAL_PARAMS_KEY)


def has_signal_params() -> bool:
    return has_value(SIGNAL_PARAMS_KEY)


def set_sar_target_positions(positions: list[int]) -> None:
    set_value(SAR_TARGET_POSITIONS_KEY, positions)


def get_sar_target_positions() -> list[int] | None:
    return get_value(SAR_TARGET_POSITIONS_KEY)


def set_sar_result(result: dict) -> None:
    set_value(SAR_RESULT_KEY, result)


def get_sar_result() -> dict | None:
    return get_value(SAR_RESULT_KEY)


def has_sar_result() -> bool:
    return has_value(SAR_RESULT_KEY)


def reset_signal_state() -> None:
    """
    Signal/Record/SAR setup 상태를 초기화한다.

    새 파일 업로드처럼 signal 분석 전체를 다시 시작해야 할 때 사용한다.
    """
    reset_stage("signal")
    reset_stage("record")
    reset_stage("sar_setup")
    reset_stage("sar")


def reset_signal_position_outputs() -> None:
    """
    POSITION이 바뀌었을 때 POSITION에 종속된 상태만 초기화한다.

    초기화:
        rlum_records
        selected_record_info
        rlum_record_plot_result

    유지:
        selected_signal_position
        signal_params

    signal_params는 여러 POSITION/record plot을 보고 정하는
    전역 SAR 설정값이므로 POSITION 변경만으로 지우지 않는다.
    """
    _reset_keys(_stage_output("signal"))
    reset_stage("record")


def reset_selected_record_outputs() -> None:
    """
    선택 record가 바뀌었을 때 record에 종속된 plot만 초기화한다.

    유지:
        rlum_records
        selected_record_info
        signal_params
    """
    _reset_keys(_stage_output("record"))


def reset_signal_record_state() -> None:
    """
    기존 signal_tab.py 호출부 호환용 wrapper.

    새 코드에서는 reset_signal_position_outputs()를 직접 쓰는 편이 더 명확하다.
    """
    reset_signal_position_outputs()

# ============================================================
# 9. 전체 리셋
# ============================================================

def reset_upload_state() -> None:
    """
    Upload 단계 전체(input/output)를 비운다.
    그에 딸린 다운스트림(signal, sar)도 함께 무효화한다.
    """
    reset_stage("upload")
    invalidate_from("upload")


def reset_all_state() -> None:
    """
    이 모듈이 소유한 key만 기본값으로 되돌린다.

    주의: st.session_state 전체를 지우지 않는다.
    (위젯 key, 채팅/에이전트 상태 등 이 모듈 밖의 상태까지 날리지 않기 위함)
    """
    _reset_keys(_all_defaults())