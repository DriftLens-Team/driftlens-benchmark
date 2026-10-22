# Legacy public log v1

기존 로그의 호환성 안내다. 현재 companion과의 agent/v1 통신 계약은 [새 계약 안내](../../docs/contracts.md)에서 확인한다.

이전 공개 로그는 log_id, timestamp, agent_id, team, request, sql, answer_text, definition_note, reported_values, referenced_concepts 열 필드였다. reported_values는 concept_id=large_orders, 음수가 아닌 정수 value, ISO week period인 객체 하나다.

UTC 월요일 시작 포함·다음 월요일 제외이며 대화 시각은 일요일 23:59:59 UTC다. 당시 truth는 log_id, ontology_version_used, drift_id, contaminated 네 필드였다.

현재는 driftlens_benchmark.contracts.legacy.load_legacy(path)로 공개 v1 형식을 읽을 수 있다. 기존 루트 public_logs 모듈은 제거했다. 부족한 truth 필드를 추측해 records/v2로 이관하지 않는다. 새 생성·탐지·채점은 records/v2를 사용한다.
