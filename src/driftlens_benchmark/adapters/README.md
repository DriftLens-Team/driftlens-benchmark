# Adapters

jsonl.py는 외부 프로세스를 호출한다. 요청마다 프로세스를 새로 시작하므로 선택 profile과 snapshot이 바뀌어도 이전 상태를 재사용하지 않는다.

입력 UTF-8 JSONL 한 건을 쓰고 EOF를 닫은 뒤, 성공 또는 오류 한 건과 종료 코드를 검사한다. 최대 줄 크기는 65,536 bytes다. 잘못된 ID/중복 응답/기간 불일치/비정상 종료/시간 초과는 실패로 기록한다. 출력 버퍼는 제한되며 stderr는 원문 대신 길이와 hash만 기록한다.

command는 인자 배열이며 shell을 사용하지 않는다. timeout은 이 요청에서 시작한 process tree를 종료한다. companion 내부 모듈을 import하지 않는다.

파일 제출/HTTP 어댑터와 상시 세션 재사용은 미구현이다. 현재 외부 챗봇은 [연결 안내](../../../docs/connecting-an-agent.md)의 프로세스 계약을 따른다.
