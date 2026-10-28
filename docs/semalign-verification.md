# SemAlign 검증 기록 — 2026-10-28

이 문서는 개발용 검증 기록이다. 실제 모델 생성, 합성 source, 결정적 fake provider를 구분한다. 실제 관측·SQL·정답·API 키는 로컬의 Git 제외 `runs/`에 보존한다.

## 데이터와 실행 범위

원천 data 기준 커밋은 `163da89d5a56f820e72f29beabc8a0e3f66d8815`이며 작업 트리에 새 의미 명세 두 파일을 추가했다. 실제 읽은 내용은 각 private manifest의 source/catalog SHA-256으로 고정한다. 원천 DB·로그·truth를 수정하거나 재생성하지 않았다. 시나리오 설명의 YAML 경고 1건은 보존했다.

| 실행 | 계획 | 시도 | 응답 성공 | 검수 통과 | 거절 | 미검증/실행 실패 |
|---|---:|---:|---:|---:|---:|---:|
| source fixture | 364 | 364 | 364 | 330 | 34 | 0 / 0 |
| 실제 companion + fake provider | 364 | 364 | 364 | 364 | 0 | 0 / 0 |
| 실제 모델 `solar-pro4-260806` | 364 | 7 | 7 | 3 | 4 | 0 / 0 |

실제 모델은 첫 주의 각 지표 한 건씩만 실행했다. 변경 후 정의, 전체 기간의 실제 모델 탐지 성능을 검증한 것은 아니다. 추가 실제 호출은 수행하지 않았다. 사용한 모델 ID·생성 설정·프롬프트/구현 hash는 해당 실행 manifest에 있다.

## 확인된 실패

- source 활성 고객 17건: 그룹 조건을 SUM으로 합산하는 형태는 빈 주에서 COUNT의 0 대신 null을 낸다.
- source 성장률 17건: 현재 주의 CASE 기본값 0이 기준 SQL의 빈 현재 주 null과 다르다.
- 실제 모델의 객단가·신규 고객: `T00:00:00Z` 문자열 경계 때문에 반례의 자정 주문이 누락됐다. 객단가 쿼리에는 SQLite ROUND도 있어 보고 단계의 ties-to-even과 구분해야 한다.
- 실제 모델의 성장률: 날짜 경계 및 전주 자료 완전성 처리가 지정 정의와 달랐다.
- 실제 모델의 평균 세율: 정수 합끼리 나누고 세금 0을 null로 바꾸는 식이 비율 의미와 달랐다.

이를 semantic drift 양성으로 바꾸지 않았다. source fixture의 주 평가는 330개 관측·93쌍·완전한 시계열 5개를 대상으로 한 부분 평가이며, 탈락 34건과 불완전 시계열 2개를 함께 표시한다.

## 개발 점수의 의미

source fixture의 semantic-combined 기준 L1/L3에서 LOG·T1·T2 F1은 1.0, L0는 coverage 0이다. L2는 SQL보다 낮은 coverage를 가진다. **SQL 검수와 탐지가 같은 의미 추출기를 쓰므로 L1/L3 점수는 개발 일관성 점검이다.** 독립 정확도로 해석하지 않는다. 각 실행·노출 수준·모델 결과를 합산하지 않는다.

실제 모델 소규모 검수 통과 3건에는 의미 변경 양성이 없다. 이 표본으로 실제 drift F1을 산출하거나 전체 모델 정확도를 추정하지 않는다.

최종 6종 반례 검사에서도 source 330/364, companion fake 364/364가 유지됐다. 두 실행의 L0~L3를 각각 끝까지 탐지·채점했다. source L2의 LOG F1/coverage는 0.8451/0.5970, T1은 0.6452/0.4086, T2는 1.0/0.4다. companion fake는 364 관측·112쌍·7개 전체 시계열이 적격이며 L1~L3에서 일관성 F1=1.0이었다. 이 companion의 설명은 현재 profile을 그대로 기록하므로 L2의 일반화 평가로 사용할 수 없다.

로컬 근거: `runs/semalign-fixture-final`, `runs/semalign-companion-final`, `runs/semalign-live-smoke-01`과 각 `*-report-L*.json`. 최종 실행의 private manifest는 source·결과 파일 hash를 고정한다. SQL 형태별 품질 집계 필드가 추가되기 전 실행에는 그 집계가 null일 수 있으며, 원본 실행 기록을 사후 수정하지 않는다.

## 재현 가능한 자동 검증

원격 Linux 통합 실행에서 Python 경로의 symlink를 실제 파일로 바꾸면 venv 대신 기본 인터프리터가 선택되는 문제가 드러났다. 호출자가 지정한 절대 경로를 그대로 사용하도록 수정했다. 이 회귀는 새 semalign-companion CI의 실제 외부 프로세스 테스트로 검사한다.

확인 결과: benchmark 전체 157 passed / 1 skipped, SQL-agent 단위 테스트 55 passed, Ruff 통과. skip은 Windows symlink 권한 조건이다. 이후 수치 진단의 초기 4개 보정값만 있는 경우를 abstain으로 보완하고 관련 20개 테스트를 재확인했다. 두 wheel 빌드와 별도 설치 경로에서 import를 확인했으며, benchmark JSON schema 31개·agent prompt 2개가 wheel에 포함되는지 검사했다. 설치 wheel의 capabilities도 v2와 7개 개념을 반환했다.

```powershell
# benchmark: 기본 검증은 API 호출 없음
$env:DRIFTLENS_SEMALIGN_AGENT_PYTHON = (Resolve-Path ../driftlens-sql-agent/.venv/Scripts/python.exe).Path
.venv/Scripts/python.exe -m pytest -q
.venv/Scripts/python.exe -m ruff check src tests examples
.venv/Scripts/python.exe -m build --wheel

# SQL-agent 저장소에서
.venv/Scripts/python.exe -m unittest discover -s tests/unit -p "test_*.py" -v
.venv/Scripts/python.exe -m build --wheel
```

`DRIFTLENS_SEMALIGN_AGENT_PYTHON`을 생략하면 새 companion 통합 테스트는 건너뛴다. 기존 C03 companion 테스트는 별도로 설치한 구형 v1 패키지로 계속 실행한다. Windows의 symlink 생성 권한이 없는 경우 해당 경로 검사 한 건이 skip된다.

테스트는 실제 private data 없이 만든 8주 자료를 사용한다. 실제 데이터와 다른 변경 개념 구성과 임계값 3을 넣었다. 손계산 기대값, JOIN 증식, 반올림, 같은 숫자의 다른 정의, 근거 충돌, 같은 drift/다른 drift의 쌍, 2주 경보·후보 초기화, 미래 view·근거·ID 누락·중복·추가, 부분 실행·적격 0건을 검증한다. 기본 테스트는 모델의 언어 이해 품질을 평가하지 않는다.

## 남아 있는 연구 범위

자유로운 SQL/자연어의 완전한 의미 이해, 독립 검수와 보류 데이터 평가, OS 격리, 여러 번의 정의 변경, 미지 지표 일반화는 지원 범위 밖이다. 현재 SQL agent의 profile-rendered 설명은 L2를 쉽게 만들 수 있다. model-generated 설명을 평가하는 비교 실험은 별도 구현과 검수가 필요하다.
