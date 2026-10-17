# 계약 v1
## 기존 공개 logs.jsonl
UTF-8, 한 줄에 JSON 객체 하나. 최상위는 다음 10개 필드만 허용한다.
log_id, timestamp, agent_id, team, request, sql, answer_text, definition_note, reported_values, referenced_concepts.
앞의 8개는 문자열이다. log_id는 비어 있지 않고 파일 내 유일하다. reported_values는 현재 시나리오 A에서 concept_id="large_orders", value=0 이상의 정수, period=ISO 연도-W주차인 객체 1개 배열이다. referenced_concepts는 ["large_orders"]이다. 기존 public_logs.py가 실제 검사 범위의 기준이며 이 문서가 검증기를 추가하지 않는다.
SQL은 실제 실행한 조회이고 reported_values는 그 결과다. 최신 정의의 별도 정답과 다르다고 관측을 제거하지 않는다. answer_text는 실제 건수만 설명하고 정의·버전·변경 정보는 넣지 않는다. definition_note와 sql의 정의 단서는 L3에서 의도적으로 공개한다. 현재 구현은 L3뿐이며 L0~L2 마스킹은 미구현이다.

UTC 월요일 00:00 포함부터 다음 월요일 제외까지 조회한다. 대화 시각은 일요일 23:59:59 UTC다. 대화 시점에 유효한 정의 하나로 주 전체를 조회한다. 변경일은 UTC 00:00 적용이며 2025-01-15 변경이면 2025-W03 전체가 v2다. 입력 시간대는 UTC로 정규화하고 naive 입력은 UTC 가정으로 기록한다.

## 비공개 평가 데이터
truth.jsonl은 log_id, ontology_version_used, drift_id, contaminated를 갖는다. 변경 전 v1/null/false, 변경 후 v2/A/true다. contaminated는 기준 v1 대비 정의 변경을 뜻하며 계산 오류·환각을 뜻하지 않는다. run.private.json 및 failures.private.jsonl도 공개 입력이 아니다. truth는 log_id로 평가 시에만 결합한다.

## 향후 프로세스 요청·응답 (미구현)
benchmark의 src/adapter.py → agent의 engine/transport.py, stdin/stdout UTF-8 JSONL 한 줄당 요청·응답 1개를 목표로 한다. 서로의 내부 모듈을 import하지 않는다. 프로세스 시작 설정은 관리자가 선택한 profile·DB·모델이며 탐지기에 전달하지 않는다.
요청 예정 필드: request_id, request, timestamp, period. 응답 예정 필드: request_id, status, observation 또는 error. observation에는 sql, answer_text, definition_note, reported_values, referenced_concepts를 둔다. adapter는 request_id와 log_id를 연결하고 공개 로깅 단계에서 정확히 10필드를 만든다. 요청·응답 봉투를 공개 로그에 그대로 저장하지 않는다.
오류 응답은 공개 성공 로그로 만들지 않고 비공개 실패 기록에 둔다. stdout은 프로토콜만, 진단은 stderr로 분리할 예정이다. 타임아웃·비정상 종료·중복 ID·형식 위반 처리는 향후 구현 대상이다. 현재 agent stdout은 이 계약을 구현하지 않는다.

## 탐지 입력·출력 계약 (향후 계획)
입력은 실험에서 선택한 L0~L3 수준의 허용 공개 로그와 기준 v1이다. L3는 현재 공개 10필드를 사용하며, L2는 SQL, L1은 정의 설명, L0는 둘 다 가리는 조건이다. 현재 구현은 L3뿐이다. L0~L2는 공개 원본의 10필드를 변경하거나 비공개 필드를 추가하는 방식이 아니라 별도 입력 투영으로 계획하며, 구체적인 마스킹 표현과 검증기는 아직 구현하지 않았다. 수준 선택과 관계없이 truth, 미래 v2, 실제 profile 및 실제 변경 시점은 입력하지 않는다.

탐지 결과는 공개 로그와 별도인 결과 레코드로 둔다.

| 필드 | 의미 |
| --- | --- |
| log_id | 판정 대상 공개 로그 식별자 |
| concept_id | 판정 대상 개념 식별자 |
| decision | drift / no_drift / abstain 중 하나; abstain은 판정 유보 |
| evidence_log_ids | 근거로 사용한 허용 공개 로그 식별자 배열 |
| evidence_summary | 허용 입력에서 도출한 판정 근거 요약 |
| score (선택) | 탐지기별 점수; 확률이라고 단정하지 않으며 범위·방향·산정 의미를 탐지기 설정/문서에서 정의 |
| estimated_change_at (향후 선택) | 추정 변화점; 실제 변경 시점을 정답에서 복사하지 않음 |

window-level 평가 방식과 변화점 허용 오차는 미확정이다. 탐지 결과가 실제로 산출되거나 평가기가 구현됐다는 뜻은 아니다. evaluator만 비공개 정답을 읽고 log_id로 결합한다. contaminated는 기준 v1 대비 업무 정의 변화이며 SQL 오류나 환각 라벨이 아니다. 생성 실패는 drift 양성으로 세지 않고 별도 실패 건수로 집계한다. 판정 유보도 drift 양성으로 자동 변환하지 않는다.
