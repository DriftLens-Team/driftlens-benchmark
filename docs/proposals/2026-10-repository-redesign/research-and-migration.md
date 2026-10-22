# 조사 근거와 이전 계획

이 문서는 승인 전 조사와 계획의 기록이다. 현재 파일 전환 결과는 [migration](../../migration.md)을 따른다. 아래 ‘이번 변경’은 제안 작성 시점을 뜻한다.

## 실제 오픈소스에서 확인한 구조

2026-10-22에 README, GitHub tree와 아래 문서를 확인했다. 특정 프레임워크에 의존하거나 저장소를 복제하는 제안이 아니라, 각 프로젝트의 책임 분리 방식을 DriftLens 규모에 맞춰 적용한 설계다.

| 프로젝트·확인 revision | 실제 확인한 구성 | 이 설계에 반영한 점 |
| --- | --- | --- |
| [SWE-bench](https://github.com/SWE-bench/SWE-bench/tree/02e7a74ffd0b707aab73d203fe87bdc7c76afc8e) | `swebench/harness/`, `swebench/inference/`, `docs/`, `tests/`; 예측 파일을 입력받아 독립 실행·채점 | agent 실행 결과와 평가기를 분리, 실행별 artifact와 실패 기록 |
| [lm-evaluation-harness](https://github.com/EleutherAI/lm-evaluation-harness/tree/d6de81643928d653435c431bae19945d41d32520) | `lm_eval/api/`, `tasks/`, `models/`, `evaluator.py`, YAML task template, 기여 문서 | 선언적인 케이스와 실행 엔진 분리, 교체 가능한 adapter/detector, 케이스 추가 절차 |
| [Spider 2.0](https://github.com/xlang-ai/Spider2/tree/cafb867313aab4e674652054198f383cf4018943) | `spider2-lite/resource/`, `evaluation_suite/gold/`, SQL/실행결과 submission 예시 | DB 자원·참조 정답·제출 SQL 분리, 실행 결과에 기반한 검수 |
| [BrowserGym](https://github.com/ServiceNow/BrowserGym) | `browsergym/`, `demo_agent/`, `docs/`, `tests/`; task 추상화와 별도 agent 실험 도구 | 환경 제공과 agent 구현의 경계, 최소 연결 예시 |

근거 문서:

- [SWE-bench evaluation guide](https://github.com/SWE-bench/SWE-bench/blob/02e7a74ffd0b707aab73d203fe87bdc7c76afc8e/docs/guides/evaluation.md)
- [lm-evaluation-harness new task guide](https://github.com/EleutherAI/lm-evaluation-harness/blob/d6de81643928d653435c431bae19945d41d32520/docs/new_task_guide.md)
- [Spider 2.0 Lite evaluation layout](https://github.com/xlang-ai/Spider2/blob/cafb867313aab4e674652054198f383cf4018943/spider2-lite/evaluation_suite/README.md)

이 설계의 `src/` layout은 위 프로젝트 모두의 공통 형식이라는 주장이 아니다. 설치 경계를 명확히 하고 현재 companion agent와 일관된 패키징을 쓰기 위한 선택이다. 초기 규모에서는 다수 배포 패키지·범용 플러그인 검색·상시 DB 서비스를 도입할 필요가 없다.

## 사용자 자료와 현행 코드의 차이

| 자료 | 확인 내용 | 설계에 미치는 영향 |
| --- | --- | --- |
| [케이스 시트](https://docs.google.com/spreadsheets/d/1Cb72YOTOXoL8SKgs7ulR0KI9WT5WsE04RsISl_SBcqA/edit?gid=1475341752) | 원본 15개 + I1–I5, 보류·쉬움·어려움·혼용 구분 | catalog에 원본 ID·상태 보존 |
| [SemAlign 설계 문서](https://docs.google.com/document/d/1RJzZjKqDIeIE_QokJdtjtV0WRs8pyqf2-XRr4ESzR6s/edit) | 6개 테이블, private truth 우선 생성, 확장된 reported_values/concept_truth | records v2와 environment 확장 |
| benchmark `e294f6d2aeb50a0a49e246f94b46ec70e0fd6b61` | 루트 네 모듈 중심 실행, `src/*.py`는 주석만 존재, 기존 truth는 네 필드 | 역할을 실제 패키지로 옮기고 진척 상태를 사실에 맞게 표시 |
| [agent](https://github.com/DriftLens-Team/driftlens-sql-agent) 로컬 `b67ec9cd8c62763ec68ca896aafeef674081c558` | 패키지·JSONL·모델 SQL 생성·3컬럼 schema 검사 구현 | benchmark README의 ‘SQL replay/import 의존’ 설명은 현행 agent와 불일치 |

Google Drive connector는 두 링크를 각각 스프레드시트/문서의 읽을 수 있는 텍스트로 반환했다. 시트의 20개 후보와 설계 문서 1–10절을 읽어 구조 설계에 사용했다. 원천 CSV 전체의 통계·라이선스·live 모델 성능을 이번 작업에서 다시 실행 검증하지 않았다.

설계 문서의 SemAlign 표기는 참고 자료의 이름으로 보존하고, 저장소·패키지·CLI 이름은 요청한 DriftLens Benchmark를 유지한다.

## 기존 파일의 처리

사용자는 저장소 전체 내용 교체를 허용했지만 최종 설계 컨펌을 요청했다. 따라서 이번 변경은 이 제안 디렉터리뿐이다. 승인 뒤에는 기능 보존을 확인하며 아래 순서로 전환한다.

| 현재 | 목표 | 처리 |
| --- | --- | --- |
| `generate.py` | `src/driftlens_benchmark/cli.py` | 새 CLI 진입점으로 대체 |
| `driftlens.py` | environments / observations / runner | 적재·응답 검수·실행을 분리; LLM 생성은 외부 agent로 이동 |
| `public_logs.py` | contracts / observations | legacy v1 입력 검증과 records v2 검증을 분리 |
| `sql_tool.py` | environments | 읽기 전용·실행 상한을 재사용해 일반화 |
| `src/*.py` 주석 파일 | 실제 `src/driftlens_benchmark/` | placeholder 삭제, 구현 단계에서 실제 모듈 추가 |
| `data/fixture_orders.csv` | `datasets/jaffle_shop/fixtures/` | 작은 합성 fixture 보존·확장 |
| `scenarios/` | `benchmarks/cases/`, `benchmarks/suites/` | 중복 경로 정리, A→C03 매핑 기록 |
| `datasets/` 설명 | dataset card·schema·mapping·source lock | 실제 재현 입력의 정본으로 확장 |
| `contracts/v1/README.md` | src 계약 + docs 안내 | 기존 링크는 전환기 안내문으로 유지, machine schema 정본은 src에 둠 |
| `configs/run.example.json` | `configs/runs/`, `configs/agents/` | 실제 CLI가 읽는 검증 가능한 설정으로 교체 |
| 루트 `test_*.py` | `tests/` | 기존 중요한 경계 검증을 이관하고 새 E2E 추가 |
| `README*`, `docs/` | 새 README·가이드 | 현재 구현/예정 분리, 외부 CSV 장문 안내는 dataset 가이드로 이동 |
| `.git/`, `LICENSE` | 유지 | 이력·저작권·기존 라이선스 보존 |
| 사용자 `.env`, `.venv`, raw CSV, `runs/` | 유지 | 생성/개인 파일을 구조 정리 과정에서 삭제하지 않음 |

승인 직전 다시 Git 상태를 확인한다. 이번 조사 시작 시 benchmark와 agent의 추적 파일 변경은 없었다. companion agent 저장소는 이 설계 작업에서 수정하지 않는다. 추후 agent 기능 확장은 해당 저장소의 별도 변경으로 다룬다.

## 승인 후 검증 기준

- 기존 fixture의 기간·금액·경계 의미 보존, 설치된 패키지에서 실행.
- C03 v1/v2와 고정군의 수작업 oracle, 실제 subprocess fake agent E2E.
- DB 키·참조 무결성, 공급품 조인 fan-out, 0/NULL, cutoff 검증.
- 공개 projection의 중첩 허용 목록·원본 값 동일성·정답 누출 검사.
- protocol timeout·bad JSON·중복 ID·실패 status가 정상 관측으로 기록되지 않음.
- detector가 truth를 받지 않고 evaluator만 정답을 결합하는 경계.
- benchmark README의 모든 실행 명령을 CI fixture로 검증. 외부 모델은 opt-in 별도 검증.

이번에는 실행 코드를 변경하지 않았으므로 런타임 회귀 테스트 대신 제안 문서의 링크·파일 범위·계약 설명을 검토한다.
