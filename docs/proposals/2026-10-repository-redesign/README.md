# DriftLens Benchmark 저장소 재설계안

상태: **2026-10-22 승인된 초기 설계 기록**. 아래 내용은 구현 전 제안 원문이며 현재 구현 상태는 [현재 아키텍처](../../architecture.md)와 [이전 내역](../../migration.md)을 따른다. 미리보기 폴더는 실제 README로 대체했다. 현재 C03 종단간 경로를 구현했고 나머지는 단계별 목표다.

## 제안의 핵심

DriftLens Benchmark를 **의미 변경 케이스와 재현 가능한 DB 환경을 제공하고, 외부 SQL 에이전트의 답변·SQL을 관측해 semantic drift 탐지 성능을 평가하는 Python 벤치마크**로 정리한다.

세 가지 자산을 명확히 구분한다.

1. `datasets/`: 고객·주문·품목·상품·공급품·매장의 사실 데이터와 DB 구성법.
2. `benchmarks/`: 같은 사실에 적용할 업무 정의, 질문, 참조 SQL, 변경 일정, 대조군.
3. `src/driftlens_benchmark/`: 환경 생성, 에이전트 연결, 관측 검수, 공개 데이터 추출, 탐지, 채점.

각 케이스마다 DB 원본을 복제하지 않는다. 공통 불변 snapshot을 재사용하고, 합성이 필요한 케이스만 명시적인 데이터 보강을 적용한다. 정의 변경은 기본적으로 SQL·업무 profile의 변경이다. DB 스키마 변경이나 숫자의 자연 변동을 의미 변경으로 자동 취급하지 않는다.

검토할 문서:

- [현재 루트 README 한국어](../../../README.ko.md)
- [현재 루트 README 영어](../../../README.md)
- [상세 아키텍처·연결·평가 설계](architecture.md)
- [케이스 목록과 구현 순서](case-catalog.md)
- [오픈소스 조사·기존 파일 이전 계획](research-and-migration.md)

## 최종 목표 구조

아래는 승인 후 구현할 목표 구조다. 이번 미리보기에는 각 주요 폴더의 README만 작성했다. 파일 이름은 제안이며 미구현 Python 파일이나 SQL을 빈 껍데기로 생성하지 않는다.

```text
driftlens-benchmark/
├── README.md                         # 영어: 목적, 현재 상태, 시작, 연결, 결과
├── README.ko.md                      # 같은 내용을 한국어로 제공
├── CONTRIBUTING.md                   # 케이스·탐지기·어댑터 기여 절차
├── AGENTS.md                         # 자동화 작업의 저장소 규칙
├── LICENSE                           # 기존 Apache-2.0 유지
├── pyproject.toml                    # 설치 가능한 src 패키지·CLI·개발 의존성
├── uv.lock                           # 재현 가능한 개발/CI 의존성
├── .gitignore
├── .github/
│   ├── README.md
│   ├── workflows/ci.yml              # 계약·fixture·오프라인 E2E·문서 검증
│   ├── ISSUE_TEMPLATE/               # 케이스 제안 / 오류 보고
│   └── pull_request_template.md
├── benchmarks/
│   ├── README.md
│   ├── catalog.yaml                 # 원본 ID, 상태, 개념, 필요한 DB·결과형
│   ├── cases/
│   │   ├── README.md
│   │   ├── C03_large_orders/
│   │   │   ├── README.md            # 경영 질문·v1/v2 차이·예시·경계 조건
│   │   │   ├── case.yaml            # 개념·결과형·필요 테이블·출처
│   │   │   ├── questions.ko.jsonl    # 정의 변경을 누설하지 않는 질문
│   │   │   ├── definitions.json     # 기준/변경 정의, 생성·평가 전용
│   │   │   ├── reference/v1.sql
│   │   │   ├── reference/v2.sql
│   │   │   └── assertions.json      # 수작업 기대값과 경계값
│   │   └── ...                      # C05/C08/C10/I1/I2/I4/I5 등
│   └── suites/
│       ├── README.md
│       ├── smoke.yaml               # C03 변경 + 동일 개념 정의 고정
│       ├── temporal-core.yaml       # 확장 DB 기반 주력 사례
│       └── temporal-challenge.yaml  # 약한 신호 사례
├── datasets/
│   ├── README.md
│   └── jaffle_shop/
│       ├── README.md                # 데이터 카드: 출처·단위·한계·라이선스
│       ├── source.lock.json         # 고정 upstream commit·파일별 hash
│       ├── schema.sql              # 6개 테이블·키·제약
│       ├── mapping.yaml            # CSV → 정규화 테이블/컬럼
│       └── fixtures/               # 자체 작성한 작은 합성 CSV 6개
├── configs/
│   ├── README.md
│   ├── runs/smoke.yaml              # suite·dataset·seed·출력 위치
│   ├── agents/sql-agent-v1.yaml     # 실행 명령·고정 revision·v1 능력
│   └── detectors/sql-rules.yaml     # 탐지기 설정만 보관
├── src/
│   ├── README.md
│   └── driftlens_benchmark/
│       ├── README.md
│       ├── __init__.py
│       ├── __main__.py
│       ├── cli.py
│       ├── runner.py               # 단계 조립·상태·실패·재현 메타데이터
│       ├── contracts/              # 버전별 JSON Schema, 타입, 검증
│       ├── environments/           # 적재·snapshot·as-of 제한·조회 도구
│       ├── adapters/               # JSONL subprocess·파일 제출·v1 변환
│       ├── observations/           # 검수·truth 구성·노출 수준별 투영
│       ├── detectors/              # 기준 탐지기·확장 인터페이스
│       └── evaluation/             # 정답 결합·지표·보고서
├── tests/
│   ├── README.md
│   ├── unit/
│   ├── contracts/
│   ├── integration/
│   └── e2e/
├── examples/
│   ├── README.md
│   ├── submissions/                # 외부 챗봇의 합성 요청·응답 예시
│   ├── custom_agent/               # 최소 JSONL 브리지
│   └── custom_detector/            # 탐지기 연결 예시
├── docs/
│   ├── README.md
│   ├── quickstart.md
│   ├── architecture.md
│   ├── datasets.md
│   ├── adding-a-case.md
│   ├── connecting-an-agent.md
│   ├── writing-a-detector.md
│   ├── evaluation.md
│   ├── contracts.md
│   └── decisions/                  # 실제로 확정된 주요 설계 결정
├── .cache/                         # 다운로드 원천·재사용 DB, Git 제외
└── runs/                           # 실행별 관측·정답·예측·보고서, Git 제외
```

## 폴더별 책임

| 폴더 | 답하는 질문 | 들어가면 안 되는 것 |
| --- | --- | --- |
| `benchmarks/` | 무엇의 의미가 어떻게 달라지는가? | 일반 실행 엔진, 실행 결과 DB |
| `datasets/` | 어떤 사실 데이터로 재현하는가? | 특정 실행의 변경일·탐지 예측 |
| `configs/` | 이번 실행에서 무엇을 선택하는가? | API 키, 케이스 정의의 복사본 |
| `src/` | 환경·실행·관측·탐지·평가를 어떻게 처리하는가? | 특정 케이스 ID에 대한 분기 누적 |
| `tests/` | 구현과 케이스 계약이 맞는가? | 실제 벤치마크 점수를 대신하는 주장 |
| `examples/` | 외부 개발자가 어떻게 연결하는가? | 진짜 실험 결과처럼 보이는 합성 수치 |
| `docs/` | 사용·확장·평가 규칙은 무엇인가? | 실제 코드와 중복되는 수동 계약 정의 |
| `.cache/`, `runs/` | 내려받거나 생성한 것은 어디에 있는가? | 추적 대상 코드, 커밋할 개인정보·키 |

## 권장 범위와 컨펌 항목

**권장안:** SQLite부터 시작하고, 외부 에이전트와 JSONL로 연결하며, C03과 정의 고정 대조군으로 전 과정을 먼저 완성한다. 이후 6개 테이블 기반 케이스를 확장한다.

- 위 폴더 구조와 패키지 이름 `driftlens_benchmark`.
- 케이스 원본 ID를 보존하는 `C01–C15`, `I1–I5` 명명.
- 현재 SQL agent v1 호환 경로와 확장 관측 records v2를 구분.
- 공개 로그는 검수된 비공개 원본에서 추출하고 탐지·채점을 분리.
- 루트 영어 README + 한국어 README, 상세 기여 문서는 우선 한국어.
- 구현 단계가 통과할 때마다 기존 대응 파일을 제거하고, Git 이력·라이선스를 유지.

이 범위를 승인하면 문서뿐 아니라 패키지 구조와 실제 실행 경로의 전환을 진행한다. PostgreSQL 서비스, HTTP 서버, 웹 UI, 전체 후보의 동시 구현은 초기 범위에 포함하지 않는다. 외부 챗봇의 직접 HTTP 연결은 실제 서비스 요구가 생기면 같은 계약 위에 어댑터로 추가한다.
