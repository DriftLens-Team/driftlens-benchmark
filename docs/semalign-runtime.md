# SemAlign 생성·검수·탐지·채점

2026-10-28 구현: `driftlens-data → driftlens-sql-agent(agent/v2) → driftlens-benchmark(records/v3, detection/v2)`를 연결했다. 기존 C03의 `run/detect/evaluate`와 agent/v1은 유지한다. 새 명령은 `run-semalign/detect-semalign/evaluate-semalign`이다.

## 필요한 저장소와 실행

data checkout에는 기존 자료와 `ontology/semantics.v1.json`, `ontology/semantics.v2.private.json`이 필요하다. 의미 명세는 data 저장소가 소유한다. 기존 입력 준비 명령은 이전 파일 구조도 계속 지원한다. [입력 준비 안내](semalign-data.md)를 참고한다.

실제 agent 모드는 `--capabilities`가 agent/v2와 semalign/v1을 선언하는 SQL agent 설치가 필요하다. C03 예제에 고정한 구형 companion은 v1용이므로 SemAlign에 그대로 사용하지 않는다. 두 저장소 각각 개발 환경에 `python -m pip install -e .`로 설치하고, agent 환경의 Python을 명시한다.

```powershell
# 원천 합성 로그를 새 기준으로 검수한다. 모델 호출 없음.
.venv/Scripts/python.exe -m driftlens_benchmark run-semalign --source ../driftlens-data --mode fixture --out runs/semalign-fixture

# 외부 SQL-agent 프로세스가 새 응답을 만든다. fake는 결정적 통신 테스트 모델이다.
.venv/Scripts/python.exe -m driftlens_benchmark run-semalign --source ../driftlens-data --mode agent --provider fake --agent-python ../driftlens-sql-agent/.venv/Scripts/python.exe --out runs/semalign-agent

.venv/Scripts/python.exe -m driftlens_benchmark detect-semalign --public runs/semalign-agent/public/L3 --detector semantic-combined --out runs/semalign-agent-predictions-L3
.venv/Scripts/python.exe -m driftlens_benchmark evaluate-semalign --run runs/semalign-agent --predictions runs/semalign-agent-predictions-L3 --out runs/semalign-agent-report.json
```

모든 출력 경로는 새 경로여야 한다. `run-semalign`은 모든 계획 관측이 검수에 통과하면 종료 코드 0, 일부만 통과하거나 `--limit`으로 일부만 실행하면 1, 설정·자료 오류면 2를 반환한다. 정상적으로 기록된 부분 실행은 `evaluate-semalign --allow-partial`로 진단한다. 실패를 성공으로 바꿔 표시하는 옵션이 아니다.

실제 모델은 실행 환경에 `UPSTAGE_MODEL`, `UPSTAGE_API_KEY`를 설정한 뒤 `--provider upstage`를 사용한다. `--model-env`, `--key-env`로 환경변수 이름을 바꿀 수 있다. `.env`를 자동 탐색하거나 키를 JSON 설정에 복사하지 않는다. `--limit 7`은 원래 364건의 계획 중 앞선 7건만 시도하므로 보고서의 planned 분모는 364로 유지된다. 실제 모델 평가와 fake 실행은 합산하지 않는다.

## 실행과 정보 경계

1. source 파일과 의미 명세의 hash를 고정하고, 요청·개념·주차·정답 대응을 검사한다.
2. 주 종료 전 주문과 연결 품목만 가진 새 snapshot을 만든다. 신규 고객과 성장률에 필요한 과거 이력을 보존한다. 상품·매장도 해당 이력에 연결된 항목만 복제한다. 금액 항등식, 비어 있지 않은 키, 외래키와 timestamp 형식을 확인한다.
3. agent에는 현재 개념의 definition/semantics 하나, 해당 개념의 허용 스키마와 snapshot을 전달한다. 원래 SQL·답변·정답·미래 profile은 요청에 넣지 않는다. 요청마다 새 프로세스를 사용한다.
4. 실제 응답을 비공개 검수하고 validated/rejected/unverified/failed를 따로 기록한다. 성공 응답은 실제 SQL·답변을 보존한다.
5. validated 관측만 L0~L3로 투영한다. 현재 baseline의 v1 의미와 schema 제약만 공개한다. 새 truth는 검수된 현재 정의와 baseline의 차이에서 만들며 원본 truth의 drift 라벨을 무검증 복사하지 않는다.

에이전트 capabilities에는 프로토콜·스키마·개념 목록 외에도 설치 버전, 구현/프롬프트 SHA-256, 생성 설정이 있다. benchmark도 실행 코드 hash를 남긴다. 진행 manifest와 요청별 private attempt 파일을 기록하므로 중단 상태가 완료로 보이지 않는다. 최종 manifest가 없는 실행은 채점하지 않는다.

실행은 `unisolated`다. SQLite 도구의 읽기 권한은 제한하지만 로컬 프로세스를 OS 수준에서 별도 격리하지는 않는다. 외부 제출의 독립 평가를 위해서는 공개 bundle만 제공하는 별도 실행 환경이 필요하다.

## 생성 검수와 독립 반례

각 관측에서 다음 항목을 별도로 확인한다.

- SQL이 지정한 의미를 구현하는지: 지원되는 SQL 전체 구조와 선언된 의미 요소 비교.
- 같은 snapshot에서 SQL, data oracle, Python 행 기반 참조 계산이 같은 보고값을 내는지.
- 구조화 값과 답변의 숫자·단위·null 표현이 실행값과 맞는지.
- definition_note가 SQL 의미와 모순되지 않는지. 설명이 모호하지만 알려진 부분에 모순이 없는 경우는 허용한다.

독립 반례 DB에는 혼합 품목·동일 품목 중복·다른 상품 유형·품목 없는 주문·매장 간 과거 이력, 빈 주, 전주 합계 0, 불완전한 전주, 2.5 cents 반올림, 세금 0인 동일 수치 사례가 있다. Python 참조 계산은 source 생성기나 agent 내부 모듈을 import하지 않는다. source oracle과 이 참조 계산이 다르면 해당 검수를 unverified로 남긴다.

`null`의 의미도 정의에 포함한다. 고객 그룹을 `COUNT`하면 빈 주에 0이지만 `SUM(condition)`은 null이다. 성장률의 `CASE ... ELSE 0`도 빈 현재 주에서 기준의 null과 달라질 수 있다. source의 `executed_on_source_csv`는 현재 DB에서 실행값을 확인했다는 출처 주장이지 이 반례 검사를 통과했다는 뜻이 아니다.

정수 센트는 Python `round`의 ties-to-even, 비율은 소수 4자리 보고 규칙을 따른다. SQLite `ROUND`를 SQL에 먼저 적용하면 같은 반올림이라는 보장이 없다. 날짜 비교는 DB의 시간대 없는 UTC 문자열에 맞춰 날짜 또는 `T00:00:00` 경계를 사용한다. 문자열 뒤 `Z`를 붙인 비교는 자정 행을 빠뜨릴 수 있다.

## 탐지 방법과 지원 범위

`semantic-sql`, `semantic-note`, `semantic-combined`, `no-drift`를 제공한다. SQL 방법은 SQLGlot AST에서 전체 SELECT·조건·JOIN·집계를 소비하고 다음 의미를 추출한다: grain, aggregation, population, measure, conditions, time_semantics, null_policy, unit.

지원하는 주요 형태는 주문 EXISTS/NOT EXISTS, JOIN 후 주문별 GROUP/HAVING 또는 COUNT DISTINCT, 주간 고객 그룹의 임의 정수 횟수 조건, 전체 이력 최초 주문, AVG와 동치인 SUM/COUNT 및 금액 항등식, 전주 대비 집계 lineage, 세금 합/세전 합 비율이다. 비재귀 CTE와 별칭을 처리한다. 현재 커밋된 364개 SQL의 구조를 읽을 수 있지만, 읽었다는 사실이 지정 정의와 일치한다는 뜻은 아니다.

임의 SQL의 완전한 동치 증명은 지원하지 않는다. 추가 필터, 지원 밖 JOIN/함수/쿼리 절, 불명확한 분모·NULL 처리, 잘못된 기간은 same으로 추정하지 않는다. 설명은 명시적인 한국어 표현의 닫힌 규칙으로 읽으며, 자유로운 자연어 전체를 이해하는 모델이 아니다. 기준 설명과 정확히 같은 문장은 공개 명세에 연결할 수 있다. 모호한 표현과 미지원 SQL은 abstain한다. SQL과 설명의 의미 요소가 충돌해도 abstain한다. L0는 숫자만으로 의미 변경을 확정하지 않는다.

- LOG: 관측 하나와 baseline의 의미 비교.
- T1: 두 관측의 의미를 직접 비교. 두 관측이 모두 drift여도 서로 다른 의미면 changed다.
- T2: 현재까지의 관측만 담은 prefix view를 순서대로 전달. 같은 변경 의미가 인접한 2주에서 확인될 때 최초 경보를 고정한다. 누락·unknown·기준 복귀·다른 의미가 끼면 후보를 초기화한다. 모든 예정 주가 baseline과 같을 때만 no_change다.

각 online view와 hash, cutoff, 단계별 제출을 보존한다. 평가기는 view가 실제 공개 prefix와 같은지, 근거가 공개 필드의 원문인지, 미래 관측을 썼는지, 최초 경보를 나중에 바꿨는지 검사한다.

## 보고서 해석

planned/attempted/successful_response/failed/validated/rejected/unverified와 개념별·SQL 형태별 검수 결과를 분리한다. LOG와 T1은 적격 관측/쌍만 평가하고, T2 주 점수에는 전체 예정 주가 적격인 시계열만 포함한다. 제외된 수와 이유를 함께 제공한다. 양성 abstain은 FN, 음성 abstain은 FP나 TN으로 세지 않는다. 잘못된 시점의 T2 경보는 FP이자 FN이다. 분모 0인 지표는 null과 사유를 반환한다.

점수는 micro, 개념별, 정의 가능한 개념만의 macro, coverage, 전체/대조군/어려운 음성 FPR을 포함한다. T2는 ±2주 시점 적중과 주 단위·실제 관측 도착 기준 경보 지연을 기록한다. 마지막 주의 미확정 변화는 abstain이다.

보고서에는 두 비교 진단도 별도로 포함한다. 숫자 진단은 처음 4개 유효 값의 median/MAD를 고정하고 `max(3×MAD, |median|×0.2, 1e-9)` 밴드의 같은 방향 이탈을 2주 확인한다. LOG도 과거 prefix를 쓰는 수치 진단이며 주 의미 탐지 순위에 넣지 않는다. DB 값 비교 진단은 비공개 v1 참조값과 관측값의 차이를 사용한다. 두 진단의 설정을 정답으로 튜닝하지 않는다.

**현재 SQL 검수와 탐지기는 의미 추출기를 공유한다.** 독립 Python 계산·반례·손계산 테스트가 있어도 공통 의미 추출 오류 가능성이 남는다. 특히 검수에 통과한 L1/L3의 높은 점수는 구현 일관성 결과이며 독립적인 탐지 정확도의 증명이 아니다. report에 이 의존성을 명시한다. 별도 검수자의 판정, 보류 SQL·표현·시나리오로 평가하기 전에는 일반화 성능을 주장하지 않는다.

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
