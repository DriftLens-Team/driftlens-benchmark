# Tests

| 경로 | 검증 |
| --- | --- |
| unit/ | 금액·날짜·snapshot·읽기 권한·SQL 의미 인식 |
| contracts/ | strict JSON/YAML, private/public 경계, 값 타입 |
| integration/ | 독립 프로세스·한 줄 framing·실패·timeout |
| e2e/ | 생성→연결→탐지→채점, control·유보·부분 실행·무결성 |

fixtures/protocol_agent.py는 테스트 전용 독립 agent다. companion test는 따로 설치한 실제 driftlens-sql-agent CLI를 fake provider로 호출한다. 실제 모델/네트워크는 테스트 중 사용하지 않는다.

실행: python -m pytest -q. companion 미설치 시 해당 테스트만 skip된다. 개발 의존성·설치 과정은 [CONTRIBUTING](../CONTRIBUTING.md)을 참고한다.
