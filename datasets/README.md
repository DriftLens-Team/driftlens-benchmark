# 데이터셋
기존 data/fixture_orders.csv는 8행 합성 경계값 fixture로 그대로 유지한다. datasets는 향후 출처·라이선스·입력 해시·컬럼 매핑·시간대·금액 단위 메타데이터 위치다. 원본 주문과 SQLite snapshot에는 truth·ontology 라벨을 넣지 않는다. jaffle-shop 원본 order_total은 정수 센트이며 staging 달러와 혼동하지 않는다. 실제 데이터 다운로드나 DB 생성은 수행하지 않는다.
