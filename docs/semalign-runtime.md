# SemAlign 생성·검수·탐지·채점

2026-10-28 구현: `driftlens-data → driftlens-sql-agent(agent/v2) → driftlens-benchmark(records/v3, detection/v2)`를 연결했다. 기존 C03의 `run/detect/evaluate`와 agent/v1은 유지한다. 새 명령은 `run-semalign/detect-semalign/evaluate-semalign`이다.

## 필요한 저장소와 실행

data checkout에는 기존 자료와 `ontology/semantics.v1.json`, `ontology/semantics.v2.private.json`이 필요하다. 의미 명세는 data 저장소가 소유한다. 기존 입력 준비 명령은 이전 파일 구조도 계속 지원한다. [입력 준비 안내](semalign-data.md)를 참고한다.

실제 agent 모드는 `--capabilities`가 agent/v2와 semalign/v1을 선언하는 SQL agent 설치가 필요하다. C03 예제에 고정한 구형 companion은 v1용이므로 SemAlign에 그대로 사용하지 않는다. 두 저장소 각각 개발 환경에 `python -m pip install -e .`로 설치하고, agent 환경의 Python을 명시한다.

```powershell
# 원천 합성 로그를 새 기준으로 검수한다. 모델 호출 없음.
.venv/Scripts/python.exe -m driftlens_benchmark run-semalign --source ../driftlens-data --mode fixture --out runs/semalign-fixture

# 외부 SQL-agent가 새 응답을 만들고 독립적인 유한 사례로 검수한다.
# fake는 결정적 통신 테스트 모델이며 실제 모델의 성능을 나타내지 않는다.
.venv/Scripts/python.exe -m driftlens_benchmark run-semalign --source ../driftlens-data --mode agent --provider fake --agent-python ../driftlens-sql-agent/.venv/Scripts/python.exe --validation-policy behavioral --progress --out runs/semalign-agent

.venv/Scripts/python.exe -m driftlens_benchmark detect-semalign --public runs/semalign-agent/public/L3 --detector semantic-combined --out runs/semalign-agent-predictions-L3
.venv/Scripts/python.exe -m driftlens_benchmark evaluate-semalign --run runs/semalign-agent --predictions runs/semalign-agent-predictions-L3 --out runs/semalign-agent-report.json
```

모든 출력 경로는 새 경로여야 한다. `run-semalign`은 모든 계획 관측이 검수에 통과하면 종료 코드 0, 일부만 통과하거나 `--limit`으로 일부만 실행하면 1, 설정·자료 오류면 2를 반환한다. 정상적으로 기록된 부분 실행은 `evaluate-semalign --allow-partial`로 진단한다. 실패를 성공으로 바꿔 표시하는 옵션이 아니다.

실제 모델은 실행 환경에 `UPSTAGE_MODEL`, `UPSTAGE_API_KEY`를 설정한 뒤 `--provider upstage`를 사용한다. `--model-env`, `--key-env`로 환경변수 이름을 바꿀 수 있다. `.env`를 자동 탐색하거나 키를 JSON 설정에 복사하지 않는다. `--limit 7`은 원래 364건의 계획 중 앞선 7건만 시도하므로 보고서의 planned 분모는 364로 유지된다. 실제 모델 평가와 fake 실행은 합산하지 않는다.

`--progress`는 요청별 진행 JSON을 stderr에 쓰고 최종 요약은 stdout에 남긴다. 기본 검수 정책은 `structural`이므로 독립 결과 검수를 사용하려면 `--validation-policy behavioral`을 명시한다.

## 실행과 정보 경계

1. source 파일과 의미 명세의 hash를 고정하고, 요청·개념·주차·정답 대응을 검사한다.
2. 주 종료 전 주문과 연결 품목만 가진 새 snapshot을 만든다. 신규 고객과 성장률에 필요한 과거 이력을 보존한다. 상품·매장도 해당 이력에 연결된 항목만 복제한다. 금액 항등식, 비어 있지 않은 키, 외래키와 timestamp 형식을 확인한다.
3. agent에는 현재 개념의 definition/semantics 하나, 해당 개념의 허용 스키마와 snapshot을 전달한다. 원래 SQL·답변·정답·미래 profile은 요청에 넣지 않는다. 요청마다 새 프로세스를 사용한다.
4. 실제 응답을 비공개 검수하고 validated/rejected/unverified/failed를 따로 기록한다. 성공 응답은 실제 SQL·답변을 보존한다.
5. validated 관측만 L0~L3로 투영한다. 현재 baseline의 v1 의미와 schema 제약만 공개한다. 새 truth는 검수된 현재 정의와 baseline의 차이에서 만들며 원본 truth의 drift 라벨을 무검증 복사하지 않는다.

에이전트 capabilities에는 프로토콜·스키마·개념 목록 외에도 설치 버전, 구현/프롬프트 SHA-256, 생성 설정이 있다. benchmark도 실행 코드 hash를 남긴다. 진행 manifest와 요청별 private attempt 파일을 기록하므로 중단 상태가 완료로 보이지 않는다. 최종 manifest가 없는 실행은 채점하지 않는다.

실행은 `unisolated`다. SQLite 도구의 읽기 권한은 제한하지만 로컬 프로세스를 OS 수준에서 별도 격리하지는 않는다. 외부 제출의 독립 평가를 위해서는 공개 bundle만 제공하는 별도 실행 환경이 필요하다.

## 생성 검수와 독립 반례

두 정책 모두 snapshot과 반례에서 SQL, data oracle, 독립 Python 행 계산의 보고값을 비교하고, 응답의 숫자·단위·null 표현이 SQL 실행값과 맞는지 확인한다.

| 정책 | 추가 검수 | 결과의 의미 |
|---|---|---|
| `structural` (기본) | SQL 전체 구조에서 추출한 의미와 지정 의미 비교, 설명의 알려진 의미가 SQL과 모순되는지 확인 | 탐지기와 추출기를 공유하는 개발 일관성 검수 |
| `behavioral` | SQL/설명 추출기로 적격 표본을 고르지 않음. 설명은 현재 profile의 정본 문장과 정확히 일치해야 함 | 독립 유한 사례에서의 결과 일치. `query_correct_for_used_definition=null`, `behavioral_agreement=true` |

`behavioral`에서 정본과 다른 설명, 독립 참조 계산의 지원 범위 밖 의미, oracle과 Python 참조 계산의 불일치는 `unverified`다. SQL 결과의 불일치는 `rejected`다. 탐지기가 읽지 못하는 SQL도 독립 결과 검수를 통과하면 공개 평가에 들어가며, 탐지의 abstain은 그대로 채점한다.

반례는 9종이다: 혼합 품목·중복·다른 상품 유형·품목 없는 주문·매장 간 이력을 포함한 혼합 사례, 빈 주, 전주 합계 0, 불완전한 전주, 전주 시작 정각·1초 후·1초 전, 2.5 cents 반올림, 세금 0. Python 참조 계산은 source 생성기나 agent 내부 모듈을 import하지 않는다. 이 유한 사례의 통과는 모든 가능한 DB에서의 SQL 동치를 증명하지 않는다.

`null`의 의미도 정의에 포함한다. 고객 그룹을 `COUNT`하면 빈 주에 0이지만 `SUM(condition)`은 null이다. 성장률의 `CASE ... ELSE 0`도 빈 현재 주에서 기준의 null과 달라질 수 있다. source의 `executed_on_source_csv`는 현재 DB에서 실행값을 확인했다는 출처 주장이지 이 반례 검사를 통과했다는 뜻이 아니다.

정수 센트는 Python `round`의 ties-to-even, 비율은 소수 4자리 보고 규칙을 따른다. SQLite `ROUND`를 SQL에 먼저 적용하면 같은 반올림이라는 보장이 없다. 날짜 비교는 DB의 시간대 없는 UTC 문자열에 맞춘다. 성장률의 전주 완전성은 `MIN(ordered_at)`과 전주 시작의 전체 timestamp를 비교해야 한다. 날짜만 비교하면 전주 시작 정각도 불완전하다고 판정한다. 문자열 뒤 `Z`를 붙인 주간 경계는 자정 행을 빠뜨릴 수 있다.

## 탐지 방법과 지원 범위

`semantic-sql`, `semantic-note`, `semantic-combined`, `no-drift`를 제공한다. SQL 방법은 SQLGlot AST에서 전체 SELECT·조건·JOIN·집계를 소비하고 다음 의미를 추출한다: grain, aggregation, population, measure, conditions, time_semantics, null_policy, unit.

지원하는 주요 형태는 주문 EXISTS/NOT EXISTS, JOIN 후 주문별 GROUP/HAVING 또는 COUNT DISTINCT, 주간 고객 그룹의 임의 정수 횟수 조건, 전체 이력 최초 주문, AVG와 동치인 SUM/COUNT 및 금액 항등식, 전주 대비 집계 lineage, 세금 합/세전 합 비율이다. 비재귀 CTE와 별칭을 처리한다. 정수 나눗셈 후 실수 변환, 그룹의 임의 날짜, 소비하지 않은 쿼리 절을 올바른 정의로 인정하지 않는다.

임의 SQL의 완전한 동치 증명은 지원하지 않는다. 추가 필터, 지원 밖 JOIN/함수/쿼리 절, 불명확한 분모·NULL 처리, 잘못된 기간은 same으로 추정하지 않는다. 설명은 명시적인 한국어 표현의 닫힌 규칙으로 읽으며, 자유로운 자연어 전체를 이해하는 모델이 아니다. 기준 설명과 정확히 같은 문장은 공개 명세에 연결할 수 있다. 각 채널에서 모호하거나 미지원이면 abstain한다. `semantic-combined`는 SQL을 읽지 못해도 설명으로 판단할 수 있으므로 SQL 해석 성능은 L1 또는 `semantic-sql` 결과를 함께 본다. SQL과 설명의 의미 요소가 충돌하면 abstain한다. L0는 숫자만으로 의미 변경을 확정하지 않는다.

- LOG: 관측 하나와 baseline의 의미 비교.
- T1: 두 관측의 의미를 직접 비교. 두 관측이 모두 drift여도 서로 다른 의미면 changed다.
- T2: 현재까지의 관측만 담은 prefix view를 순서대로 전달. 같은 변경 의미가 인접한 2주에서 확인될 때 최초 경보를 고정한다. 누락·unknown·기준 복귀·다른 의미가 끼면 후보를 초기화한다. 모든 예정 주가 baseline과 같을 때만 no_change다.

각 online view와 hash, cutoff, 단계별 제출을 보존한다. 평가기는 view가 실제 공개 prefix와 같은지, 근거가 공개 필드의 원문인지, 미래 관측을 썼는지, 최초 경보를 나중에 바꿨는지 검사한다.

## 보고서 해석

planned/attempted/successful_response/failed/validated/rejected/unverified와 개념별·SQL 형태별 검수 결과를 분리한다. LOG와 T1은 적격 관측/쌍만 평가하고, T2 주 점수에는 전체 예정 주가 적격인 시계열만 포함한다. 제외된 수와 이유를 함께 제공한다. 양성 abstain은 FN, 음성 abstain은 FP나 TN으로 세지 않는다. 잘못된 시점의 T2 경보는 FP이자 FN이다. 분모 0인 지표는 null과 사유를 반환한다.

점수는 micro, 개념별, 정의 가능한 개념만의 macro, coverage, 전체/대조군/어려운 음성 FPR을 포함한다. T2는 ±2주 시점 적중과 주 단위·실제 관측 도착 기준 경보 지연을 기록한다. 마지막 주의 미확정 변화는 abstain이다.

보고서에는 두 비교 진단도 별도로 포함한다. 숫자 진단은 처음 4개 유효 값의 median/MAD를 고정하고 `max(3×MAD, |median|×0.2, 1e-9)` 밴드의 같은 방향 이탈을 2주 확인한다. LOG도 과거 prefix를 쓰는 수치 진단이며 주 의미 탐지 순위에 넣지 않는다. DB 값 비교 진단은 비공개 v1 참조값과 관측값의 차이를 사용한다. 두 진단의 설정을 정답으로 튜닝하지 않는다.

manifest의 `validation_scope`와 보고서의 `validation_policy`, `validation_dependence`, `accuracy_claim`을 점수와 함께 읽는다. **`structural` 점수는 공유 추출기에 의한 개발 일관성 결과다.** `behavioral`은 이 선택 의존성을 제거하지만 유한 사례에서 일치한 출력의 탐지 성능만 측정한다. 두 정책의 점수를 합산하지 않는다. 현재 agent의 `profile_rendered` 설명은 L2/L3를 쉽게 만들 수 있으며 자유 자연어의 이해 성능이 아니다. 별도 검수자의 판정과 보류 SQL·표현·시나리오 평가 전에는 일반화 성능을 주장하지 않는다.

## 전체 인수 검증과 증적

세 저장소의 개발 환경을 준비한 뒤 benchmark 저장소에서 실행한다. 아래 명령은 테스트·코드 검사·빌드, 독립 참조 검사, 새 폴더의 데이터 재생성, 원본 fixture·재생성 fixture·fake agent의 전체 기간 실행과 L0~L3 채점을 기록한다. 원본 data 파일은 덮어쓰지 않는다.

```powershell
.venv/Scripts/python.exe scripts/run_semalign_acceptance.py --data-root ../driftlens-data --data-python ../driftlens-data/.venv/Scripts/python.exe --agent-python ../driftlens-sql-agent/.venv/Scripts/python.exe --out runs/semalign-acceptance-offline
```

실제 모델의 364건 생성도 실행하려면 환경변수를 준비하고 다음 명령을 사용한다. 명시한 파일에서는 `UPSTAGE_MODEL`과 `UPSTAGE_API_KEY`만 읽으며 기존 환경변수가 우선한다. API 호출이 발생한다.

```powershell
.venv/Scripts/python.exe scripts/run_semalign_acceptance.py --data-root ../driftlens-data --data-python ../driftlens-data/.venv/Scripts/python.exe --agent-python ../driftlens-sql-agent/.venv/Scripts/python.exe --out runs/semalign-acceptance-live --live --env-file ../driftlens-sql-agent/.env
```

fixture 두 실행은 `structural`, fake와 실제 모델은 `behavioral`이다. `execution.json`에 실제 명령·시각·종료 코드·소요 시간을, `logs/`에 각 명령의 stdout/stderr를 보존한다. 생성 종료 코드 1인 부분 실행도 원인과 제외 수를 남기고 `--allow-partial`로 채점한다. 전체 절차의 `completed`는 모든 생성물이 검수에 통과했다는 뜻이 아니다.

완료한 실행에서 열람용 증적을 만든다. 아래 예는 실제 모델 L1/L3 보고서를 포함하며, `--report`와 `--test-log`는 여러 번 지정할 수 있다. 출력 폴더는 새 경로여야 한다.

```powershell
.venv/Scripts/python.exe scripts/semalign_evidence.py --run runs/semalign-acceptance-live/live --out runs/semalign-evidence-live --execution runs/semalign-acceptance-live/execution.json --report runs/semalign-acceptance-live/live-report-L1.json --report runs/semalign-acceptance-live/live-report-L3.json --test-log runs/semalign-acceptance-live/logs/benchmark-tests.stdout.txt
```

`index.html`은 검수 수·채점 결과·생성 SQL/답변·실행 기록을 보여준다. `generated.csv`에는 모든 시도와 실패 이유, `observations.jsonl`에는 적격 공개 관측, `result.json`에는 집계, `execution.txt`에는 재현 명령과 선택한 테스트 로그를 저장한다. 스크린샷은 이 실제 결과 화면에서 캡처하고, 원본 파일과 함께 제공한다.

## 산출물

```text
run/
├─ private/
│  ├─ manifest.json                 # 계획·시도·품질·출처·hash
│  ├─ planned.jsonl, planned-pairs.jsonl
│  ├─ attempts.jsonl, attempts/     # 성공·실패·검수 결과
│  ├─ truth.jsonl, pairs.truth.jsonl, series.truth.jsonl
│  ├─ snapshots/, counterexamples/
│  └─ requests/                    # agent의 현재 profile·config·요청
└─ public/L0..L3/                  # baseline, logs, pairs, series, manifest
predictions/
├─ manifest.json, log.jsonl, pairs.jsonl, series.jsonl
├─ online.jsonl
└─ online/<concept>/<step>.json     # 그 시점까지의 입력만 저장
```

DB·정답·응답·키·실행 결과는 Git에 넣지 않는다. [검증 기록](semalign-verification.md)은 집계와 재현 절차만 기록한다. 원래 C03 경로는 회귀와 호환성에 필요하므로 삭제하지 않았다.
