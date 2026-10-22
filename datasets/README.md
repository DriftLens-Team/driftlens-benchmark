# Datasets

사실 데이터의 출처와 재현 환경을 관리한다. 업무 정의·변경 일정·정답은 이 폴더에 넣지 않는다.

[jaffle_shop](jaffle_shop/README.md)의 자체 합성 주문 8건과 3컬럼 SQLite schema를 제공한다.

실행 DB는 runs/<id>/environment에 생성되고 Git에서 제외된다. 원천 파일과 schema는 checksum으로 고정한다. 외부 CSV로 바꾸려면 dataset 설정과 source lock을 함께 준비한다.
