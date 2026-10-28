# SemAlign data 연결과 입출력 계약

이 문서는 **입력 준비 명령**의 계약을 설명한다. `driftlens-data` 파일을 읽고 정합성을 검사해 agent/v2 요청과 records/v3 합성 fixture를 만든다. 후속 생성·검수·탐지·채점은 [SemAlign 전체 실행](semalign-runtime.md)에 구현했다. 기존 C03의 agent/v1 → records/v2 실행·탐지·채점도 유지한다.

`prepare-data` 자체는 SQL 생성·검수·snapshot·정답 생성·채점을 수행하지 않는다. `status=prepared`는 생성·평가 완료를 의미하지 않는다. 이 작업은 새 `run-semalign` 이후 명령으로 수행한다.

## 실행

저장소의 개발 환경을 설치한 뒤, benchmark 루트의 PowerShell에서 실행한다. source는 로컬 data checkout 또는 동일 파일 구조의 내보내기 폴더다. 매번 새로운 out 경로를 사용한다.

```powershell
.venv/Scripts/python.exe -m driftlens_benchmark inspect-data --source ../driftlens-data
.venv/Scripts/python.exe -m driftlens_benchmark prepare-data --source ../driftlens-data --out runs/semalign-inputs
```

첫 명령은 읽기 전용 검사와 개수 요약만 수행한다. 두 번째 명령은 같은 검사를 통과한 자료를 새 폴더에 내보낸다. API 키와 네트워크 호출은 필요하지 않고, data 저장소의 Python 모듈이나 생성기를 import/실행하지 않는다. source 내부에 out을 만들거나 기존 out을 덮어쓰는 것은 거부한다.

현재 고정 데이터에서는 7개 개념·52주·364건·112쌍이 나온다. 네 노출 수준은 같은 표본의 파생본이다. 원천 변경 후에도 이 숫자를 고정 출력하는 것이 아니라 시나리오 기간과 실제 레코드에서 계산한다. SemAlign v0.1의 개념 7개, 개념당 16쌍, 변경 개념당 양성 8쌍이라는 형식은 검증한다.

## 읽는 자료와 검사

- `ontology/v1.yml`, `ontology/v2.yml`, `ontology/scenario.private.yml`, `schema.sql`.
- `data/jaffle.sqlite`, `data/logs.L0.jsonl`~`logs.L3.jsonl`.
- `data/truth.jsonl`, `data/pairs.jsonl`, `data/pairs_truth.jsonl`.
- 7개 개념·명목 단위·주간 기간·변경일의 정합성, 개념별 모든 주의 1:1 대응.
- JSON/YAML 중복 키, NaN/Infinity, 추가 공개 중첩 필드, ID 중복·누락, 로그 순서.
- 네 수준에서 가린 필드 외 내용과 ID 순서가 같은지 확인.
- truth의 버전·개념·대조군 여부·변경 라벨이 source 시나리오와 맞는지 확인.
- 쌍의 실제 로그 연결, 같은 개념, 1~8주 간격, 변경·사업 사건·어려운 음성 라벨 검증.
- SQLite 읽기 전용 quick_check, 필수 테이블의 열 이름, 외래키 검사. 로그 SQL이나 oracle SQL은 실행하지 않는다.

파일은 source 루트 안에서만 읽고 symlink 등을 통해 루트 밖으로 나간 자산은 거부한다. 로드 전후 모든 원천 파일의 hash가 같은지 확인한다. commit은 Git checkout일 때 기록하며, 수정된 작업 트리도 포함한 실제 파일의 정본은 `source_files_sha256`이다. commit만으로 파일 내용을 보증하지 않는다.

현재 source의 flow-style YAML note 한 곳에는 따옴표 없는 쉼표 때문에 null 값의 추가 키가 생긴다. 필수 시나리오 필드는 엄격히 검사하되, 문자열 note와 함께 나타난 **추가 null 주석 키만** private `source_warnings`에 보존한다. CLI에는 `source_warning_count`를 표시한다. 값이 있는 알 수 없는 키, 필수 필드 누락, 중복 키는 거부한다. 원본 주석 수정은 data 측 후속 작업이다.

이 단계의 검사 범위는 `structure_and_alignment`다. source의 `executed_on_source_csv` 표시는 upstream 출처 주장으로 private에 보존할 뿐, benchmark의 새로운 SQL 의미 검수 결과로 승격하지 않는다.

## 산출물과 공개 범위

```text
runs/semalign-inputs/
├─ private/
│  ├─ manifest.json
│  ├─ agent-v2.requests.jsonl
│  └─ source-fixture.private.jsonl
└─ public/
   ├─ L0/
   ├─ L1/
   ├─ L2/
   └─ L3/
      ├─ manifest.json
      ├─ baseline.json
      ├─ logs.jsonl
      ├─ pairs.jsonl
      └─ series.json
```

각 L 폴더는 같은 다섯 파일을 갖는다. public에는 v1의 concept_id/label/definition/unit와 관측·쌍·시계열 인덱스만 있다. ontology의 oracle_sql, v2, 변경일, 난이도, 정답, source 경로는 내보내지 않는다. baseline의 구조화된 의미 요소와 required_slots 컴파일은 다음 탐지 구현 단계의 작업이다.

L0는 SQL/정의 설명을 모두 null로, L1은 설명만, L2는 SQL만 가리고 L3는 둘 다 유지한다. 같은 source ID에 대해 결정적인 새 log_id를 발급하고 쌍과 시계열 참조도 함께 바꾼다. agent request_id는 이 log_id와 같으며 source ID와 정답의 대응은 private에 보관한다. 원본 SQL·답변·정답을 agent 요청에 넣지 않는다.

각 공개 manifest에는 `source_mode=synthetic_fixture`, `stage=data_preparation`, `generation_validation=not_run`을 명시하고 네 자료 파일의 SHA-256을 기록한다. private manifest는 source 파일과 준비 산출물의 hash, 입력 가정·경고 및 개수를 기록한다. 아직 주간 DB를 복제하거나 정식 `truth.jsonl`을 만들지 않는다.

읽기 API:

```python
from driftlens_benchmark.datasets.semalign import load_source, prepare_source
from driftlens_benchmark.observations.projection import load_fixture_bundle

source = load_source("../driftlens-data")
print(source.summary())
prepare_source("../driftlens-data", "runs/new-inputs")
bundle = load_fixture_bundle("runs/new-inputs/public/L0")
```

bundle reader는 hash·노출 수준·중첩 계약·ID·쌍/시계열 연결을 재검사한다. 기존 `detect/evaluate`는 records/v2 전용이다. records/v3은 `run-semalign/detect-semalign/evaluate-semalign`을 사용하며 준비 자료를 검수 완료 실행으로 취급하지 않는다.

## agent/v2

요청은 정확히 `request_id`, `request`, `timestamp`, `concept_id`, `window`, `as_of`의 여섯 필드다. 현재 profile과 DB 설정은 요청 본문으로 변경할 수 없다.

```json
{
  "request_id": "req-demo-001",
  "request": "지난주 매출 성장률 알려줘",
  "timestamp": "2024-09-10T14:00:00Z",
  "concept_id": "sa_revenue_growth_wow",
  "window": {"start": "2024-09-02T00:00:00Z", "end": "2024-09-09T00:00:00Z"},
  "as_of": "2024-09-09T00:00:00Z"
}
```

window는 월요일 00:00 UTC부터 다음 월요일 제외이며 as_of는 end와 같다. timestamp는 질문 시각을 유지하고 end 이상이어야 한다. source의 날짜만 있는 window/as_of는 UTC 자정으로 변환한다. 시간대 없는 질문 시각은 UTC로 가정했다는 개수를 private에 기록한다. 소수 초를 조용히 절삭하지 않으며 현재 계약에서 거부한다.

성공 응답 봉투는 `request_id/status=ok/observation`, 오류는 `request_id/status=error/error`다. observation은 sql, answer_text, definition_note, reported_values, referenced_concepts 다섯 필드이며, result는 다음 형태다.

```json
{
  "result_id": "r1",
  "concept_id": "sa_revenue_growth_wow",
  "type": "metric_value",
  "value": null,
  "unit": "ratio",
  "window": {"start": "2024-09-02T00:00:00Z", "end": "2024-09-09T00:00:00Z"},
  "as_of": "2024-09-09T00:00:00Z"
}
```

count는 0 이상의 정수 토큰, cents는 정수 토큰, ratio는 소수 4자리 이내의 유한 숫자이며 음수도 허용한다. null은 표현 가능하지만 실제로 계산 불가인지 판단하는 것은 후속 생성 검수 책임이다. bool, 정수처럼 보이는 count의 3.0, NaN/Infinity는 거부한다. `referenced_concepts` 및 unit은 concept_id와 일치해야 한다.

JSON Schema와 교차 필드 검사를 함께 사용한다.

```python
from driftlens_benchmark.contracts.semalign import request_check, response_check
from driftlens_benchmark.adapters.jsonl import exchange

request_check(request)
response_check(response, request)
# command는 실제 agent/v2를 지원하는 실행 파일이어야 한다.
observation, diagnostics = exchange(command, request, cwd=workspace, timeout=60, protocol="agent/v2")
```

exchange의 기본값은 agent/v1이다. 자동 추정이나 v1로의 대체 실행은 없다. v2 응답의 요청 ID·개념·window·as_of가 요청과 다르면 거부한다. 독립 프로세스 테스트와 실제 companion의 fake provider로 이 경계를 확인했다. v2 대응 companion과 새 profile을 명시적으로 선택해야 한다.

## records/v3와 detection/v2

records/v3은 공개 관측, baseline, pair, series, manifest와 검수 결과의 private truth/attempt 스키마를 제공한다. 공개 최상위 10필드를 유지하며 hidden 필드는 생략하지 않고 null로 둔다. 입력 준비 baseline은 설명형이며, 검수 완료 bundle에는 data 소유의 의미 요소·required_slots·schema·평가 기간을 추가한다.

detection/v2는 LOG, T1, T2의 제출 형식을 검증한다. LOG는 drift/no_drift/abstain, T1은 changed/unchanged/abstain, T2는 change/no_change/abstain이다. T2의 change는 월요일인 estimated_change_at과 그 이후의 alarm_at이 필요하고, 다른 상태의 날짜는 null이어야 한다. 새 evaluator는 근거의 존재·미래 시점·허용 채널·전체 ID 집합·online prefix·최초 경보도 검사한다. 스키마 검사만으로 제출 검증이 끝나는 것은 아니다.

## 검증과 제한

테스트는 private data 저장소 없이도 실행하도록 독립적인 8주 합성 source를 만든다. 실제 모델과 companion 코드를 import하지 않는다. 실제 data checkout에 대한 inspect/prepare 및 네 공개 수준의 readback은 별도 로컬 통합 점검으로 수행한다.

전체 pytest, Ruff, wheel build는 [개발 안내](../CONTRIBUTING.md)를 따른다. 입력 준비 테스트는 실제 모델 품질이나 탐지 성능을 검증하지 않는다. 이후 구현과 실제 실행의 검증 결과는 [검증 기록](semalign-verification.md), 전체 방향은 [설계안](semalign-design.md)을 참고한다.

2026-10-28 **첫 입력 준비 단계** 확인 결과(후속 검증은 [별도 기록](semalign-verification.md)):

- 전체 테스트 **121 passed, 1 skipped**. skip은 Windows에서 symlink를 만들 권한이 없는 환경의 경로 검사다.
- Ruff와 wheel build 통과. 빌드된 wheel에서 직접 import하여 새 스키마 10개가 포함되고 로드되는지 확인했다.
- data commit `163da89d5a56f820e72f29beabc8a0e3f66d8815`의 364건·112쌍을 준비하고 L0~L3 모두 다시 읽었다. 원본 data 작업 트리는 변경하지 않았다.
- source 주석 경고 1건을 기록했다. 실제 agent/v2 모델 실행과 새 채점은 수행하지 않았다.
