# Observations

sql_semantics.py는 SQLGlot AST에서 제한된 orders/COUNT/주간 범위/정수 임계값 형태를 해석한다. 조건 순서·괄호·alias·비교 방향 차이는 허용하지만 일반 SQL 동등성을 보장하지 않는다.

records.py는 실제 쿼리 결과, 적용 정의의 참조 결과, 답변 숫자를 검수한다. semantic_drift, output_changed, query_correct_for_used_definition, answer_matches_query_result를 분리한다. 실제 reported value가 재실행 값과 맞는지도 private에 기록한다.

private truth가 원본이다. validated 레코드만 nested schema로 검증해 public으로 복사하며 값을 다시 계산하거나 고치지 않는다. rejected/unverified 레코드는 private와 집계 분모에 남는다. 현재 공개 수준은 L3만 지원한다.
