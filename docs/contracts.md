# Contracts

정본은 [src/driftlens_benchmark/contracts](../src/driftlens_benchmark/contracts/README.md)이며 wheel에 JSON Schema를 포함한다.

| 버전 | 대상 |
| --- | --- |
| agent/v1 | companion의 기존 네 필드 요청과 응답 봉투 |
| records/v2 | 확장된 result_id/window/as_of, private concept_truth, 공개 manifest |
| detection/v1 | 예측과 공개 근거 |
| records/v1 | 과거 공개 로그의 명시적 읽기 검증 |
| agent/v2 | SemAlign의 개념/window/as_of 요청·응답과 명시적 프로세스 연결 경계 |
| records/v3 | SemAlign 공개 bundle·의미 명세·private truth/attempt·쌍/시계열 정답 |
| detection/v2 | LOG/T1/T2 제출·실행 manifest·online prefix와 경보 검증 |
| semantics/v1 | data 소유의 기준/현재 의미 명세와 스키마 제약 |

새 계약의 예시는 [SemAlign data 연결](semalign-data.md), 실행·검수는 [SemAlign 전체 실행](semalign-runtime.md)을 따른다. 새 companion은 agent/v2를 명시적으로 지원하며 capabilities로 확인한다. 기존 v1 companion은 계속 v1 전용이다.

SemAlign의 `validated`는 해당 실행의 검수 정책에 통과했다는 뜻이다. `structural`의 공개 `validation_scope`는 `meaning_and_execution`, `behavioral`은 `behavioral_agreement`다. 후자는 `query_correct_for_used_definition=null`, `behavioral_agreement=true`를 기록하며 유한 사례의 결과 일치를 SQL 동치 증명으로 승격하지 않는다. 평가기는 공개 scope, 비공개 실행 정책과 각 attempt의 검수 필드를 교차 검사한다.

아래 실행·private truth 설명은 기존 C03의 agent/v1·records/v2 기준이다.

agent/v1 요청에는 새 records 버전 필드를 넣지 않는다. runner가 period를 UTC 주간 window와 as-of로 변환한다. 주 시작 포함·다음 월요일 제외, timestamp는 일요일 23:59:59Z다.

v2 공개 최상위는 log_id, timestamp, agent_id, team, request, sql, answer_text, definition_note, reported_values, referenced_concepts의 열 필드다. 중첩 구조도 strict하게 검사한다.

private truth는 공개 필드 전체와 concept_truth/validation_status/execution을 가진다. 검증 성공은 true, 실패는 false, 지원되지 않아 미검증이면 null이다. 현재 scalar large_orders 1개 결과만 지원한다.

legacy import 예:

```python
from driftlens_benchmark.contracts.legacy import load_legacy
rows = load_legacy("path/to/old/logs.jsonl")
```

이 함수가 과거 truth를 새로운 concept_truth로 바꾸지는 않는다. records/v3 입력 준비는 비율을 표현할 수 있지만 기존 C03 실행·채점에는 적용하지 않는다. 월간·다중 결과·ranking은 아직 지원하지 않는다.
