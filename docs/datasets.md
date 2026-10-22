# Dataset setup

기본 데이터는 [자체 합성 8행 fixture](../datasets/jaffle_shop/README.md)다. 네트워크 다운로드 없이 C03을 실행한다.

외부 주문 CSV/JSONL에는 id, ordered_at, order_total이 필요하다. 금액은 cents 정수, 시각은 UTC로 정규화한다. 입력 날짜 범위가 요청한 모든 주를 포함해야 한다. 날짜 범위 검사 자체가 빠진 거래가 없음을 보증하지는 않는다.

다른 입력을 쓰려면 dataset.yaml을 복사해 orders/schema/source_lock 경로를 설정하고, source.lock.json에 dataset_id, provenance, files.orders와 files.schema의 SHA-256을 기록한다. suite의 dataset 경로를 바꾼다. provenance에는 원천 URL·고정 commit·다운로드 조건·합성 여부를 남긴다. config 경로는 각각의 설정 파일 기준이다.

파일 checksum이 달라졌는데 같은 lock을 유지하면 validate/run이 실패한다. 원천과 schema를 바꿀 때 의미·단위·결과 기대값도 재검증해야 한다. 외부 source에 fixture의 3/2/3/4 건수를 기대하지 않는다.

agent DB에는 order_id, ordered_at, order_total_cents 세 컬럼이 있다.

SQL 방언은 SQLite다. 외부 원천의 재배포 권한을 프로젝트 코드 라이선스에서 추론하지 않는다.
