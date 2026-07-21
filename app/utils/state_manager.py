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

# signal_params 중 De 값을 실제로 바꾸는 항목.
# 나머지(reference_*)는 출처 기록용이라 바뀌어도 SAR 결과는 유효하다.
DE_AFFECTING_PARAMS = ("signal_integral", "background_integral")



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
# depends_on에는 "내가 직접 쓰는 stage"만 적는다. 간접 의존은 자동으로 따라간다.
# 순서가 아니라 의존 관계가 기준이므로, 정의 순서를 바꿔도 무효화 결과는 같다.
#
# 예) signal(어느 POSITION 곡선을 볼지)은 sar가 의존하지 않는다.
#     POSITION을 바꿔도 이미 돌려둔 SAR 결과는 살아남아야 하기 때문이다.

SESSION_SCHEMA: dict[str, dict] = {
    "upload": {
        "depends_on": [],
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
        "depends_on": ["upload"],
        "input": {
            SELECTED_SIGNAL_POSITION_KEY: None,
        },
        "output": {
            RLUM_RECORDS_KEY: None,
        },
    },
    "record": {
        "depends_on": ["signal"],
        "input": {
            SELECTED_RECORD_INFO_KEY: None,
        },
        "output": {
            RLUM_RECORD_PLOT_RESULT_KEY: None,
        },
    },
    "sar_setup": {
        "depends_on": ["upload"],
        "input": {
            SIGNAL_PARAMS_KEY: None,
        },
        "output": {},
    },
    "sar": {
        "depends_on": ["sar_setup"],
        "input": {
            SAR_TARGET_POSITIONS_KEY: None,
        },
        "output": {
            SAR_RESULT_KEY: None,
        },
    },
}


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
    for stage in SESSION_SCHEMA:
        merged.update(_stage_all(stage))
    return merged


def _dependents_of(stage: str) -> list[str]:
    """
    stage에 직접·간접으로 의존하는 stage 전부를 스키마 정의 순서로 반환한다.

    depends_on을 거꾸로 따라간다. 이미 찾은 stage는 다시 타지 않으므로
    스키마에 순환이 생겨도 무한 재귀에 빠지지 않는다.
    """
    found: set[str] = set()

    def walk(target: str) -> None:
        for name, spec in SESSION_SCHEMA.items():
            if target in spec["depends_on"] and name not in found:
                found.add(name)
                walk(name)

    walk(stage)

    return [name for name in SESSION_SCHEMA if name in found]


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
      - 그 stage에 의존하는 모든 stage를 input/output 통째로 비운다

    "뒤에 있는 것"이 아니라 "나에게 의존하는 것"이 기준이다.
    예) invalidate_from("signal")은 record만 비운다. sar_setup과 sar는
        signal에 의존하지 않으므로 POSITION을 바꿔도 살아남는다.

    새 stage를 추가해도 이 함수는 수정할 필요가 없다.
    스키마에 depends_on만 적으면 된다.
    """
    # 현재 stage: output만 비운다 (input은 방금 갱신했으므로 보존)
    _reset_keys(_stage_output(stage))

    # 나에게 의존하는 stage: input + output 전부 비운다
    for dependent in _dependents_of(stage):
        _reset_keys(_stage_all(dependent))


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
    """
    확인할 POSITION을 저장하고, 여기에 의존하는 결과를 무효화한다.

    POSITION이 바뀌면 그 POSITION의 record 목록과 곡선 그림은 무의미해진다.
    반면 signal_params와 SAR 결과는 signal에 의존하지 않으므로 살아남는다.
    """
    changed = get_value(SELECTED_SIGNAL_POSITION_KEY) != position
    set_value(SELECTED_SIGNAL_POSITION_KEY, position)

    if changed:
        invalidate_from("signal")


def get_selected_signal_position() -> int | None:
    return get_value(SELECTED_SIGNAL_POSITION_KEY)


def set_rlum_records(records: dict) -> None:
    set_value(RLUM_RECORDS_KEY, records)


def get_rlum_records() -> dict | None:
    return get_value(RLUM_RECORDS_KEY)


def has_rlum_records() -> bool:
    return has_value(RLUM_RECORDS_KEY)


def set_selected_record_info(record_info: dict) -> None:
    """
    확인할 record를 저장하고, 여기에 의존하는 결과를 무효화한다.

    record가 바뀌면 그 record로 그린 곡선 그림만 무의미해진다.
    """
    changed = get_value(SELECTED_RECORD_INFO_KEY) != record_info
    set_value(SELECTED_RECORD_INFO_KEY, record_info)

    if changed:
        invalidate_from("record")


def get_selected_record_info() -> dict | None:
    return get_value(SELECTED_RECORD_INFO_KEY)


def set_rlum_record_plot_result(result: dict) -> None:
    set_value(RLUM_RECORD_PLOT_RESULT_KEY, result)


def get_rlum_record_plot_result() -> dict | None:
    return get_value(RLUM_RECORD_PLOT_RESULT_KEY)


def has_rlum_record_plot_result() -> bool:
    return has_value(RLUM_RECORD_PLOT_RESULT_KEY)


def set_signal_params(params: dict) -> None:
    """
    SAR 파라미터를 저장한다.

    파라미터가 실제로 바뀌었을 때만 다운스트림(sar)을 무효화한다.
    integral이 바뀌면 기존 SAR 결과의 De는 다른 조건으로 계산된 값이므로
    화면에 남아 있으면 안 된다.

    같은 값으로 다시 저장하는 경우까지 무효화하면 수 분짜리 SAR 실행 결과를
    이유 없이 날리게 되므로 비교 후 분기한다.

    dict 전체가 아니라 DE_AFFECTING_PARAMS만 비교한다. params의 reference_*
    항목은 "어느 POSITION의 곡선을 보고 정했는지" 기록용이라 화면 표시에만
    쓰이고 run_sar_analysis에는 전달되지 않는다 (sar_tab.py의 실행부 참고).
    다른 record를 둘러보다 같은 integral로 다시 저장했을 때 SAR 결과가
    날아가면 안 된다.
    """
    old = get_signal_params() or {}
    changed = any(old.get(k) != params.get(k) for k in DE_AFFECTING_PARAMS)

    set_value(SIGNAL_PARAMS_KEY, params)

    if changed:
        invalidate_from("sar_setup")


def get_signal_params() -> dict | None:
    return get_value(SIGNAL_PARAMS_KEY)


def has_signal_params() -> bool:
    return has_value(SIGNAL_PARAMS_KEY)


def set_sar_target_positions(positions: list[int]) -> None:
    """
    SAR 분석 대상 POSITION을 저장한다.

    이 호출은 곧 재실행이 시작된다는 뜻이므로 옛 SAR 결과를 먼저 버린다.
    분석이 예외로 실패했을 때 이전 실행의 De 표가 화면에 남는 것을 막는다.
    (signal_params와 달리 값 비교 가드를 두지 않는다. 같은 POSITION으로
     다시 실행하는 경우에도 결과는 새로 계산되기 때문이다.)
    """
    set_value(SAR_TARGET_POSITIONS_KEY, positions)
    invalidate_from("sar")


def get_sar_target_positions() -> list[int] | None:
    return get_value(SAR_TARGET_POSITIONS_KEY)


def set_sar_result(result: dict) -> None:
    set_value(SAR_RESULT_KEY, result)


def get_sar_result() -> dict | None:
    return get_value(SAR_RESULT_KEY)


def has_sar_result() -> bool:
    return has_value(SAR_RESULT_KEY)


# ============================================================
# 9. 전체 리셋
# ============================================================

def reset_all_state() -> None:
    """
    이 모듈이 소유한 key만 기본값으로 되돌린다.

    주의: st.session_state 전체를 지우지 않는다.
    (위젯 key, 채팅/에이전트 상태 등 이 모듈 밖의 상태까지 날리지 않기 위함)
    """
    _reset_keys(_all_defaults())


# ============================================================
# 10. 셀프 체크
# ============================================================
# 분기가 있는 로직이므로 최소 확인 하나를 남긴다.
# 실행: venv/bin/python app/utils/state_manager.py

if __name__ == "__main__":
    init_session_state()

    # depends_on에 오타가 나면 그 stage는 아무에게도 무효화되지 않고
    # 조용히 옛 값을 들고 있게 된다. 이 모듈이 막으려는 바로 그 상황이라
    # 이름이 실제 stage인지부터 확인한다.
    for _name, _spec in SESSION_SCHEMA.items():
        for _dep in _spec["depends_on"]:
            assert _dep in SESSION_SCHEMA, \
                f"{_name}의 depends_on에 없는 stage '{_dep}'이 적혀 있다"

    # 의존 그래프가 의도한 모양인지 먼저 확인한다.
    # 이게 틀리면 아래 무효화 동작은 전부 의미가 없다.
    assert _dependents_of("upload") == ["signal", "record", "sar_setup", "sar"], \
        "새 파일 업로드는 모든 단계를 무효화해야 한다"
    assert _dependents_of("signal") == ["record"], \
        "POSITION 변경이 SAR까지 건드리면 안 된다"
    assert _dependents_of("record") == [], \
        "record 선택 변경은 자기 그림 외에 아무것도 건드리지 않는다"
    assert _dependents_of("sar_setup") == ["sar"], \
        "integral 변경은 SAR 결과를 무효화해야 한다"
    assert _dependents_of("sar") == [], \
        "sar 뒤에는 아직 아무 단계도 없다"

    # POSITION을 바꿔도 integral과 SAR 결과는 살아남아야 한다 (예외 함수를
    # 손으로 만들었던 이유. 이제 규칙에서 자동으로 나온다)
    set_value(SIGNAL_PARAMS_KEY, {"signal_integral": "1:2"})
    set_value(SAR_RESULT_KEY, {"de": 42})
    set_value(RLUM_RECORDS_KEY, {"record_index": [1]})
    set_selected_signal_position(99)

    assert get_value(SIGNAL_PARAMS_KEY) == {"signal_integral": "1:2"}, \
        "POSITION 변경에 integral 설정이 날아갔다"
    assert get_value(SAR_RESULT_KEY) == {"de": 42}, \
        "POSITION 변경에 SAR 결과가 날아갔다"
    assert get_value(RLUM_RECORDS_KEY) is None, \
        "POSITION이 바뀌었는데 옛 record 목록이 남아 있다"

    # 새 파일 업로드는 반대로 전부 날려야 한다
    set_current_sample({"raw_path": "x"}, "a.bin", "hash1")
    assert get_value(SIGNAL_PARAMS_KEY) is None, \
        "새 파일인데 옛 integral 설정이 남아 있다"
    assert get_value(SAR_RESULT_KEY) is None, \
        "새 파일인데 옛 SAR 결과가 남아 있다"

    # 위에서 상태를 어지럽혔으므로 다시 초기화하고 이어서 확인한다
    _reset_keys(_all_defaults())

    p1 = {"reference_position": 1, "signal_integral": "1:2", "background_integral": "900:1000"}
    p2 = {"reference_position": 7, "signal_integral": "1:2", "background_integral": "900:1000"}
    p3 = {"reference_position": 7, "signal_integral": "1:5", "background_integral": "900:1000"}

    set_signal_params(p1)
    set_value(SAR_RESULT_KEY, {"de": 100})

    # 같은 값 재저장 -> SAR 결과 유지
    set_signal_params(p1)
    assert get_sar_result() == {"de": 100}, "같은 파라미터 재저장에 결과가 날아갔다"

    # reference_*만 변경 -> De에 영향 없으므로 SAR 결과 유지
    set_signal_params(p2)
    assert get_sar_result() == {"de": 100}, "reference_* 변경만으로 SAR 결과가 날아갔다"

    # integral 변경 -> SAR 결과 무효화
    set_signal_params(p3)
    assert get_sar_result() is None, "integral이 바뀌었는데 옛 SAR 결과가 남아 있다"

    # SAR 재실행 시작 -> 옛 결과는 버린다
    set_value(SAR_RESULT_KEY, {"de": 200})
    set_sar_target_positions([1, 2, 3])
    assert get_sar_result() is None, "SAR 재실행 시작인데 옛 결과가 남아 있다"

    print("state_manager self-check OK")
