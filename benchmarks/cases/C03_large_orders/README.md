# C03 · 대형 주문

같은 ‘대형 주문’이 주문 총액 **2,000 cents 이상(v1)**에서 **3,000 cents 이상(v2)**으로 바뀌는 사례다. 총액 단위는 정수 cents이며 임계값은 포함한다.

- [case.yaml](case.yaml): 케이스 자산 연결.
- [definitions.json](definitions.json): 업무 정의 정본.
- [questions.ko.jsonl](questions.ko.jsonl): 현재 fake agent가 지원하는 질문.
- [reference/v1.sql](reference/v1.sql), [reference/v2.sql](reference/v2.sql): UTC 주간 [start, end) 참조 SQL.
- [assertions.json](assertions.json): 수작업 기대값.

1900·2000·2500·3000 cents 주문 4건이면 v1=3, v2=1이다. 포함 경계와 집계 단위를 검증하는 예시다.

smoke fixture에서는 첫 주 v1=3/v2=1, 둘째 주 v1=4/v2=2다. 변경군은 3→2, 정의 고정군은 3→4다. 두 군에 같은 데이터·기간·질문을 사용한다.

현재 관측은 주간 정수 건수만 지원한다. SQL은 실제 실행 결과와 답변을 검수한 뒤 공개한다. 지원하지 않는 의미 구조는 ‘정답 SQL과 같은 숫자’여도 검증 완료로 처리하지 않는다.

출처: [Drifts Data v0.1](https://docs.google.com/spreadsheets/d/1Cb72YOTOXoL8SKgs7ulR0KI9WT5WsE04RsISl_SBcqA/edit?gid=1475341752), ID 03.
