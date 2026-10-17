# DriftLens Benchmark

[English](README.md) | [한국어](README.ko.md)

업무 정의의 변화를 연구하기 위해 SQL 실행 결과에 근거한 로그를 재현 가능하게 생성합니다. 시나리오 A에서는 `large_orders`의 기준을 주문 금액 2,000센트 이상에서 3,000센트 이상으로 변경합니다.

## 주요 기능

- CSV·JSONL 주문 데이터를 읽고 SQLite로 주간 건수를 계산합니다.
- 고정 템플릿 또는 Upstage 모델로 한국어 답변을 생성합니다.
- 공개 관측 로그와 비공개 정답·실패·실행 메타데이터를 분리합니다.
- 답변 숫자를 실제 SQL 결과와 대조하고 대표적인 정의 정보 누출 표현을 검사합니다.
- 연동 에이전트에 엄격한 공개 로그 로더와 실행 범위가 제한된 읽기 전용 SQLite 도구를 제공합니다.

## 요구사항과 시작하기

Python 3.11 이상이 필요합니다. 로컬 템플릿 실행에는 Python 표준 라이브러리만 사용합니다. 저장소 루트에서 PowerShell로 실행합니다.

```powershell
python -m unittest -v
python generate.py --orders data/fixture_orders.csv --start 2025-01-06 --weeks 2 --out runs/demo
```

8행 합성 fixture는 기본 변경일인 2025-01-15를 기준으로 **3건과 2건**을 생성합니다. 전체 jaffle-shop 데이터셋이 아니며, 템플릿 답변은 LLM 생성 데이터가 아닙니다.

실행마다 새로운 출력 디렉터리를 지정해야 합니다. 이미 존재하는 디렉터리는 거부됩니다. 요청한 주간 전체가 원본 데이터의 날짜 범위 안에 있어야 합니다.

모델로 답변을 생성하려면 `UPSTAGE_API_KEY`와 `UPSTAGE_MODEL`을 외부에서 설정하고 생성 명령에 `--mode llm`을 추가합니다. `--model`은 모델 환경변수보다 우선합니다. 계정에서 지원하는 모델을 사용해야 합니다. 실제 제공자 호환성과 답변 품질은 아직 검증되지 않았으며, 모의 HTTP 테스트가 이를 보장하지는 않습니다. 자격정보와 생성된 비공개 데이터는 버전 관리에 포함하지 마세요.

## 외부 CSV 사용하기

처음에는 동봉된 fixture만으로 실행할 수 있습니다. 외부 합성 데이터를 사용하려면 **benchmark 저장소 루트**에서 PowerShell로 다음 순서를 따르세요.

![외부 데이터에서 로컬 CSV, benchmark 출력으로 이어지는 흐름과 형제 저장소 배치](docs/assets/data-flow.png)

*실행 화면이 아닌 설정 안내도입니다. agent는 생성된 공개 로그와 SQLite 스냅샷을 사용하며 CSV를 직접 읽지 않습니다.*

### 1. 원본과 버전 확인

원본은 가상의 상점 데이터를 다루는 dbt 실습 저장소 [dbt-labs/jaffle-shop](https://github.com/dbt-labs/jaffle-shop/blob/5beb145b00f5465ec759cfcdd9745e858818cf95/README.md)입니다. 이 안내는 commit [`5beb145b00f5465ec759cfcdd9745e858818cf95`](https://github.com/dbt-labs/jaffle-shop/commit/5beb145b00f5465ec759cfcdd9745e858818cf95)의 [`seeds/jaffle-data/raw_orders.csv`](https://github.com/dbt-labs/jaffle-shop/blob/5beb145b00f5465ec759cfcdd9745e858818cf95/seeds/jaffle-data/raw_orders.csv)를 고정해 사용합니다. 실험 재현에는 내용이 바뀔 수 있는 `main` URL을 피하세요.

필요한 파일은 이 CSV 하나입니다. 이 방식에서는 외부 dbt 프로젝트를 clone하거나 실행하지 않아도 되며 dbt Cloud·웨어하우스·외부 프로젝트 의존성 설치도 필요하지 않습니다. GitHub HTML 페이지가 아닌 원본 CSV를 내려받으세요.

**출처와 라이선스:** 고정 commit의 저장소 트리에 라이선스 파일이 없고 GitHub에도 감지된 저장소 라이선스가 없습니다. 별도 데이터 라이선스도 확인하지 못했습니다. 공개되어 있다는 사실만으로 재배포 허용을 확인한 것은 아니므로, 이용 목적에 맞는 허용 여부는 원본 프로젝트에 확인하세요. 이 저장소는 출처만 연결하고 해당 CSV를 재배포하지 않습니다. DriftLens의 Apache-2.0 라이선스가 외부 데이터의 라이선스를 정하는 것은 아닙니다.

### 2. 지정 경로에 다운로드

원본의 `seeds/jaffle-data/raw_orders.csv`를 로컬 `driftlens-benchmark/data/raw_orders.csv`에 저장합니다. 고정된 원본 파일은 헤더와 값을 그대로 사용하면 되며 변환이 필요하지 않습니다. 이 로컬 경로는 이미 Git 제외 대상입니다.

```powershell
$sourceCommit = '5beb145b00f5465ec759cfcdd9745e858818cf95'
$sourceUrl = "https://raw.githubusercontent.com/dbt-labs/jaffle-shop/$sourceCommit/seeds/jaffle-data/raw_orders.csv"
if (Test-Path -LiteralPath 'data/raw_orders.csv') { throw 'data/raw_orders.csv already exists; verify or choose another filename.' }
Invoke-WebRequest -Uri $sourceUrl -OutFile 'data/raw_orders.csv'
Get-Content -LiteralPath 'data/raw_orders.csv' -TotalCount 1
Get-FileHash -LiteralPath 'data/raw_orders.csv' -Algorithm SHA256
```

예상 헤더는 다음과 같습니다.

```text
id,customer,ordered_at,store_id,subtotal,tax_paid,order_total
```

예상 SHA256: `E8EE89233D417FD695D016588649C008D930110D50027480BB95B443EC0DC76B`. 값이 다르면 파일 내용이 다른 것이므로 사용 전에 URL과 파일을 확인하세요. 원본 commit과 해시를 실험 기록에 남기세요. 생성기도 입력 SHA256을 비공개 실행 메타데이터에 기록합니다.

고정 파일에는 2024-09-01부터 2025-08-31까지의 데이터 61,948행이 있습니다. 헤더·날짜 범위·해시는 확인했지만, 이 파일을 사용한 전체 benchmark 실행은 아직 검증되지 않았습니다.

### 3. 컬럼 확인 후 실행

| 원본 CSV 컬럼 | 필요한 의미와 로컬 매핑 |
| --- | --- |
| `id` | 중복 없는 주문 식별자. SQLite의 `order_id`로 적재 |
| `ordered_at` | ISO 시각. UTC 날짜로 정규화 |
| `order_total` | 정수 센트. `order_total_cents`로 적재 |
| 나머지 컬럼 | 허용하지만 현재 로더에서는 사용하지 않음 |

원본 시각에는 시간대 오프셋이 없어 DriftLens에서는 UTC로 해석합니다. 원본 프로젝트의 [staging SQL](https://github.com/dbt-labs/jaffle-shop/blob/5beb145b00f5465ec759cfcdd9745e858818cf95/models/staging/stg_orders.sql)은 달러 컬럼도 만들므로, **raw 센트 필드 대신 staging의 달러 `order_total`을 사용하면 안 됩니다.** 현재 로더에는 설정으로 CSV 컬럼명을 바꾸거나 통화 단위를 변환하는 기능이 없습니다.

```powershell
python generate.py --orders data/raw_orders.csv --start 2025-01-06 --weeks 2 --effective-at 2025-01-15 --out runs/jaffle-demo
```

템플릿 모드로 실행하며 월요일부터 확인된 날짜 범위 안의 2개 주 전체를 조회합니다. 사용하지 않은 출력 디렉터리를 지정하세요. 성공하면 `runs/jaffle-demo/` 아래에 공개 로그 2건, 대응하는 비공개 정답 2건, 비어 있는 실패 파일, 실행 메타데이터와 `orders.sqlite`가 생깁니다. 외부 데이터의 건수는 fixture의 3건·2건과 다르며, 여기서는 외부 데이터의 실제 건수를 제시하지 않습니다.

### 4. 설정 오류 해결

| 증상 | 확인할 내용 |
| --- | --- |
| CSV를 찾지 못함 | benchmark 루트에서 실행하고 `data/raw_orders.csv`를 확인하세요. 다른 위치라면 실제 경로를 `--orders`에 지정하세요. |
| 필수 컬럼 누락·CSV 파싱 오류 | HTML이 아닌 raw 파일을 받았는지 확인하고 `id, ordered_at, order_total`을 유지하세요. 다른 데이터셋의 사전 정리는 로더 밖에서 해야 합니다. |
| 금액이 정수가 아님·예상 밖 건수 | staging 달러가 아닌 원본 정수 센트를 사용하세요. v1/v2 임계값은 2,000/3,000센트입니다. |
| 날짜 범위·월요일 오류 | 월요일 시작과 원본 범위 안의 완전한 주를 선택하세요. 위 예시는 고정 파일 범위에 들어갑니다. |
| 출력 디렉터리가 이미 있음 | 새로운 `--out` 경로를 선택하세요. 재실행만을 위해 결과를 삭제하지 마세요. |
| agent에서 benchmark 모듈 import 실패 | 형제 체크아웃과 agent README의 `PYTHONPATH` 또는 로컬 패키지 설치 안내를 확인하세요. |
| agent가 입력을 열지 못함 | 먼저 생성한 뒤 `--logs`와 `--db`가 같은 실행 디렉터리를 가리키게 하세요. |

## 입력과 출력

주문 입력에는 `id`, `ordered_at`, `order_total`이 필요합니다. 금액은 달러가 아닌 **정수 센트**입니다. 시간대가 있는 시각은 UTC로 정규화하고, 시간대가 없는 시각은 UTC로 해석합니다.

| 출력 | 내용과 접근 범위 |
| --- | --- |
| `logs.jsonl` | 공개 L3 관측 로그 |
| `truth.jsonl` | `log_id`로 연결하는 비공개 정답 |
| `run.private.json` | 원본 해시·임계값·변경일·모드/모델·시간 규칙·성공/실패 수를 담은 비공개 기록 |
| `failures.private.jsonl` | 비공개 생성 실패 기록. 실패한 답변을 몰래 고치지 않음 |
| `orders.sqlite` | 정답·온톨로지 라벨이 없는 원본 주문 스냅샷 |

생성 실패가 있으면 종료 코드 1을 반환합니다. 공개 로그의 최상위 필드는 정확히 다음 10개입니다.

```text
log_id, timestamp, agent_id, team, request, sql, answer_text,
definition_note, reported_values, referenced_concepts
```

`reported_values`에는 실제 SQL 결과의 개념·값·ISO 주차 관측을 담습니다. 최신 업무 정의를 따로 계산한 정답이 아니므로, 이전 정의를 사용한 SQL도 유효한 관측으로 유지합니다.

조회 기간은 UTC 월요일 00:00 포함부터 다음 월요일 제외까지입니다. 대화 시각은 일요일 23:59:59 UTC이며, 그 시점에 유효한 정의 하나를 주 전체에 적용합니다. 변경은 UTC 자정부터 적용되므로 2025-01-15 변경이면 2025-W03에 v2를 적용합니다.

비공개 정답 필드는 `log_id`, `ontology_version_used`, `drift_id`, `contaminated`입니다. 변경 전 라벨은 v1/null/false, 변경 후는 v2/A/true입니다. `contaminated`는 v1 대비 정의 변경을 뜻하며 SQL 오류나 환각을 뜻하지 않습니다.

필드 규칙과 계획된 탐지 인터페이스는 [계약 문서](contracts/v1/README.md)를 참고하세요. 탐지기는 허용된 공개 로그와 기준 v1만 받아야 하며, 비공개 정답·미래 정의·실제 profile·변경 시점은 받지 않아야 합니다. 파일 분리와 공개 로더가 프로세스 수준의 접근 통제를 대신하지는 않습니다. L3에서는 SQL과 정의 단서가 의도적으로 공개됩니다.

## 저장소 구조

| 경로 | 역할 |
| --- | --- |
| `generate.py`, `driftlens.py` | 생성 CLI와 구현 |
| `public_logs.py`, `sql_tool.py` | 공개 입력 검증과 읽기 전용 SQLite |
| `data/`, `test_*.py` | 합성 fixture와 오프라인 테스트 |
| `contracts/`, `docs/` | 계약과 아키텍처 |
| `datasets/`, `scenarios/`, `configs/` | 데이터셋·시나리오 설명과 향후 설정 예시 |
| `src/` | 실행 관리·adapter·logging·탐지·평가의 주석 전용 예정 파일 |

역할 분담, 독립적인 버전 기록, 정보 경계는 [아키텍처 안내](docs/README.md)를 참고하세요.

## 연동 에이전트와 현재 상태

[DriftLens SQL Agent](https://github.com/DriftLens-Team/driftlens-sql-agent)는 공개 로그의 SQL을 스냅샷에서 재실행하고 답변의 일관성을 검사합니다. 현재 이 저장소의 로더·SQL 도구·검수 함수를 import합니다. 질문만으로 SQL을 독립 생성하는 구현은 아닙니다.

별도 프로세스 JSONL 연결, 외부 profile 기반 엔진, L0~L2 입력 투영, 정의 고정 대조군 실행, 드리프트 탐지와 채점은 계획 단계입니다. 현재 CLI는 설정 예시 파일을 읽지 않습니다.

오프라인 테스트는 경계값·재현성·모의 모델 응답·공개/비공개 분리·SQL 제한을 다룹니다. 전체 jaffle-shop 실행과 실제 모델 동작은 아직 검증되지 않았습니다. 숫자 추출 능력은 평가하지 않으며, 자동 답변 검사가 모든 의미적 누출을 배제하지는 않습니다.

## 라이선스

[Apache License 2.0](LICENSE)
