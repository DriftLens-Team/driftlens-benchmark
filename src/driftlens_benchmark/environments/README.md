# Environments

build.py는 입력 주문을 UTC 날짜·정수 cents로 정규화하고, 보고 주 종료일 전에 있는 이력만 불변 snapshot으로 만든다. C03의 실제 3컬럼 orders 테이블을 사용한다.

sql.py는 읽기 전용 URI, SQLite authorizer, 행 수·VM step·시간 상한으로 SQL 검수 범위를 제한한다. orders와 COUNT만 허용한다. 생성 연결을 외부 코드에 노출하지 않는다.

다른 프로세스의 파일 쓰기를 OS에서 막지는 않는다. runner는 agent 실행 전후 hash를 비교한다. 6개 테이블/다른 DB 방언은 아직 지원하지 않는다.
