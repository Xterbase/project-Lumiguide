# app/utils/state_manager.py

from __future__ import annotations

import streamlit as st


# ============================================================
# 0. session_state key 상수
# ============================================================
# 문자열 오타 방지 + 호출부 가독성을 위해 상수로 관리한다.

UPLOADED_SAMPLE_KEY = "uploaded_sample"
UPLOADED_FILE_NAME_KEY = "uploaded_file_name"
POSITION_RESULT_KEY = "position_result"


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
        },
        "output": {
            POSITION_RESULT_KEY: None,
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

def set_current_sample(sample: dict, uploaded_file_name: str) -> None:
    """
    현재 업로드된 sample 정보를 저장하고,
    이전 파일 기준으로 계산된 모든 다운스트림 결과를 무효화한다.
    """
    set_value(UPLOADED_SAMPLE_KEY, sample)
    set_value(UPLOADED_FILE_NAME_KEY, uploaded_file_name)
    invalidate_from("upload")


def get_current_sample() -> dict | None:
    return get_value(UPLOADED_SAMPLE_KEY)


def has_current_sample() -> bool:
    return has_value(UPLOADED_SAMPLE_KEY)


def get_uploaded_file_name() -> str | None:
    return get_value(UPLOADED_FILE_NAME_KEY)


def is_new_uploaded_file(uploaded_file_name: str) -> bool:
    """
    현재 업로드된 파일이 기존 파일과 다른지 확인한다.

    지금 Version1에서는 파일명 기준으로만 판단한다.
    (동명이파일·내용변경은 추후 내용 해시 비교로 확장 예정)
    """
    return (
        get_value(UPLOADED_SAMPLE_KEY) is None
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
# 8. 전체 리셋
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