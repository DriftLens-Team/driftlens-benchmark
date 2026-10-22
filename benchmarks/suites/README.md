# Suites

[smoke.yaml](smoke.yaml)은 2025-01-06부터 두 주 동안 C03 변경군과 정의 고정군을 실행한다. 변경군의 정의는 2025-01-13부터 v2이며 control은 계속 v1이다. 이 날짜는 개발 fixture용 선택이다.

suite 경로는 파일 위치 기준으로 해석한다. UTC 일요일 23:59:59의 현재 정의를 보고 주 전체에 적용한다. 시작은 월요일이며 변경 전/후 보고가 모두 존재해야 한다.

현재는 development split, L3, C03, control=true만 허용한다. 아직 없는 temporal-core/challenge 설정은 만들지 않았다. 선언만 추가해 지원하지 않는 케이스를 실행할 수는 없다.
