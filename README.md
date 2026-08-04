# LumiGuide

루미네선스(OSL/TL) 연대 해석 워크플로 보조 도구.

분석 파이프라인을 시각화하고, 등가선량(De) 분포의 특성(과분산·왜도·다봉성)을 바탕으로
통계 연령모델(CAM / MAM / FMM) 선택을 돕는다. 통계 계산 자체는 R `Luminescence`
패키지가 담당하며, 이 프로젝트는 그 통계를 재구현하지 않는다 — `rpy2`로 R을 호출한다.

사용자·소스 주석 소통 언어는 한국어다.

## 무엇을 하는가

원시 데이터 → 신호 분석 → De 분포 분석 → 모델 추천 → (예정) 연령 계산 → 결과·보고서로
이어지는 워크플로를 단계별 탭으로 제공한다. 목표는 "De 분포를 보고 어떤 모델을 쓸지"라는
연구자 판단에 남는 불확실성을, 워크플로 표준화·시각화와 근거 있는 추천으로 줄이는 것이다.

**모델 추천은 결정적(deterministic)이다.** 같은 입력 + 같은 임계값이면 항상 같은 모델을
낸다 — 연대값이 출판되려면 재현 가능해야 하기 때문이다. 추천은 연구자 판단을 대체하지 않고,
근거 지표를 함께 제시해 돕는 가이드다.

## 현재 상태

| 단계 | 탭 | 상태 |
|---|---|---|
| 1 | Data Upload & Inspect | 구현됨 |
| 2 | Signal Analysis | 구현됨 |
| 3 | SAR Analysis | 구현됨 (De 값, QC 분류, 성장곡선, CSV) |
| 4 | De Distribution | 구현됨 (분포 지표 + CAM/MAM/FMM 추천) |
| 5 | Model Recommendation | 자리표시자 — 추천 로직은 현재 4번 탭 안에 있음 |

### 알려진 한계 (읽고 시작할 것)

- **다봉 데이터의 MAM/FMM 구분을 아직 신뢰하지 말 것.** 추천 결정 트리가 양의 왜도
  게이트를 다봉(FMM) 게이트보다 먼저 평가한다. 로그정규 분포는 부분 표백과 무관하게
  선형 도메인에서 양의 왜도를 갖기 때문에, 진짜 다성분 혼합이 MAM으로 오분류될 수 있다.
  게이트 순서 변경은 출판되는 연대값에 영향을 주므로 전문가 검토 후로 재설계를 연기했다.
- **음수/0 De는 지원하지 않는다.** 로그 기반 모델을 적용할 수 없어 명시적으로 중단한다.
  관례상 음수 De는 버리지 않고 unlogged 모델로 다루지만(Galbraith & Roberts 2012),
  그 경로는 아직 미구현이다.
- **single-grain(multi-GRAIN) 파일은 차단된다.** 조용히 틀린 곡선을 그리는 것을 막은
  상태이며, 지원한 것이 아니다. MAM/FMM의 주 대상 데이터라 향후 우선 과제다.

## 요구 사항

- Python 3.14 (프로젝트 자체 virtualenv 사용)
- R 설치 + `Luminescence` 패키지 (시스템에 설치되어 있어야 `rpy2`가 호출 가능)

R 쪽 준비:

```r
install.packages("Luminescence")
```

## 설치 · 실행

```bash
source venv/bin/activate          # virtualenv 활성화
pip install -r requirements.txt   # 의존성 설치/갱신
streamlit run app/main.py         # 앱 실행 (주 진입점)
```

`requirements.txt`는 코드가 실제로 import하는 것만 담는다(`pandas`, `rpy2`, `streamlit`).

## 구조

`rpy2`로 이어지는 3계층. 데이터는 **UI → utils → R** 방향으로 흐른다.

```
app/main.py            Streamlit 진입: 페이지 설정, 사이드바, 5개 워크플로 탭
  └─ app/tabs/         탭당 모듈 하나 (upload / signal / sar / de 구현됨)
       └─ app/utils/   브리지 + 상태 계층
            └─ R/pipeline.R   Luminescence 패키지 안에서 도는 R 함수들
```

- **`app/utils/r_runner.py`** — R로 들어가는 유일한 통로. rpy2는 스레드 안전하지 않아
  모든 R 접근은 여기의 잠금(`R_LOCK`) 패턴을 통해야 한다. 탭에서 직접 R을 부르지 말 것.
- **`R/pipeline.R`** — 분석 함수. Risø `.bin`/`.rda`/`.rdata`를 읽고, 위치·레코드를
  요약하고, 곡선을 그리고, SAR와 De 분포 분석을 수행한다.
- **`app/utils/state_manager.py`** — 파이프라인을 의존 그래프가 있는 stage로 모델링한다.
  한 stage의 입력이 바뀌면 그 stage의 출력과 그것에 (직·간접으로) 의존하는 모든 stage가
  무효화된다. stage를 추가하려면 `SESSION_SCHEMA`에 `depends_on`과 함께 항목만 추가하면 된다.
- **`app/utils/file_utils.py`** — 업로드·결과 저장. 분석 결과는 세션 상태만이 아니라
  디스크(`outputs/samples/{sample_id}/`)에도 반드시 기록한다(프로젝트 요구사항).

더 자세한 설계 배경과 함정은 `CLAUDE.md`에 있다.

## 검증

테스트 프레임워크·린터는 두지 않는다. 대신 각 `app/utils/` 모듈이 `__main__`에
`assert` 기반 셀프 체크를 담는다. 직접 실행한다:

```bash
venv/bin/python app/utils/state_manager.py
venv/bin/python app/utils/model_recommend.py
venv/bin/python app/utils/r_runner.py     # R + Luminescence 설치 필요, 약 2초
```

`r_runner.py`의 셀프 체크는 Luminescence 내장 예제(`CWOSL.SAR.Data`)로 픽스처를
그때그때 생성하므로 저장소에 커밋된 데이터가 필요 없다.
