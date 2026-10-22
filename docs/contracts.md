# Contracts

정본은 [src/driftlens_benchmark/contracts](../src/driftlens_benchmark/contracts/README.md)이며 wheel에 JSON Schema를 포함한다.

| 버전 | 대상 |
| --- | --- |
| agent/v1 | companion의 기존 네 필드 요청과 응답 봉투 |
| records/v2 | 확장된 result_id/window/as_of, private concept_truth, 공개 manifest |
| detection/v1 | 예측과 공개 근거 |
| records/v1 | 과거 공개 로그의 명시적 읽기 검증 |

agent/v1 요청에는 새 records 버전 필드를 넣지 않는다. runner가 period를 UTC 주간 window와 as-of로 변환한다. 주 시작 포함·다음 월요일 제외, timestamp는 일요일 23:59:59Z다.

v2 공개 최상위는 log_id, timestamp, agent_id, team, request, sql, answer_text, definition_note, reported_values, referenced_concepts의 열 필드다. 중첩 구조도 strict하게 검사한다.

private truth는 공개 필드 전체와 concept_truth/validation_status/execution을 가진다. 검증 성공은 true, 실패는 false, 지원되지 않아 미검증이면 null이다. 현재 scalar large_orders 1개 결과만 지원한다.

legacy import 예:

```python
from driftlens_benchmark.contracts.legacy import load_legacy
rows = load_legacy("path/to/old/logs.jsonl")
```

이 함수가 과거 truth를 새로운 concept_truth로 바꾸지는 않는다. 월간·다중 결과·ranking·비율은 확장 계약이 필요하다.
