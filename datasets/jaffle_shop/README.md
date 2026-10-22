# Jaffle Shop · C03 fixture

[fixtures/orders.csv](fixtures/orders.csv)는 **자체 작성 합성 주문 8건**이다.

| 파일 | 역할 |
| --- | --- |
| [dataset.yaml](dataset.yaml) | dataset ID, 입력, schema, lock 연결 |
| [schema.sql](schema.sql) | agent v1이 요구하는 3컬럼 실제 테이블 |
| [source.lock.json](source.lock.json) | 입력·schema SHA-256과 provenance |
| [fixtures/orders.csv](fixtures/orders.csv) | 두 주의 금액 경계값 |

입력 id → order_id, ordered_at → UTC 날짜, order_total → order_total_cents로 변환한다. 금액은 정수 cents다. offset 없는 시각은 UTC로 가정하고 private manifest에 기록한다. 중복/빈 ID·비정수·무한 금액·빈 입력을 거부한다. C03은 UTC 날짜 단위이며 시간 내 변화는 지원하지 않는다.

각 보고 주의 종료일 전에 있는 주문만 snapshot에 담는다. 이전 이력은 유지하고 다음 주 주문은 제외한다. DB에는 정의·변경일·정답을 넣지 않는다. 같은 주의 변경/고정군은 같은 snapshot을 사용한다.

importer는 주문 CSV/JSONL을 지원한다. 포함된 합성 fixture는 프로젝트 Apache-2.0 라이선스를 따른다.
