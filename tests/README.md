# Tests

| 경로 | 검증 |
| --- | --- |
| unit/ | 금액·날짜·snapshot·읽기 권한·SQL 의미 인식 |
| contracts/ | strict JSON/YAML, private/public 경계, 값 타입 |
| integration/ | 독립 프로세스·한 줄 framing·실패·timeout |
| e2e/ | 생성→연결→탐지→채점, control·유보·부분 실행·무결성 |

fixtures/protocol_agent.py는 테스트 전용 독립 agent다. companion test는 따로 설치한 실제 driftlens-sql-agent CLI를 fake provider로 호출한다. 실제 모델/네트워크는 테스트 중 사용하지 않는다.

SemAlign 검사는 fixtures/semalign_source.py의 독립적인 합성 자료와 protocol_agent_v2.py를 사용한다. private data checkout 없이 새 계약, 날짜/단위/null, 노출 수준, 정답·쌍 연결, 변조·누설 거부 및 v2 프로세스 응답의 요청 일치를 검증한다. OS에서 symlink 생성을 허용하지 않으면 해당 경로 검사만 skip한다.

실행: python -m pytest -q. companion 미설치 시 해당 테스트만 skip된다. 개발 의존성·설치 과정은 [CONTRIBUTING](../CONTRIBUTING.md)을 참고한다.

전체 SemAlign 실행은 `fixtures/semalign_evaluation.py`의 독립 8주 자료로 검사한다. 손계산·반례 DB, SQL 의미, LOG/T1/온라인 T2, 첫 경보 고정, 누설·변조, 부분 실행의 분모를 검증한다. `DRIFTLENS_SEMALIGN_AGENT_PYTHON`에 v2 companion 환경의 Python 경로를 설정하면 실제 외부 CLI의 fake provider로 56건을 추가 검증한다. 설정하지 않으면 이 통합 테스트만 skip한다. 실제 데이터·모델 검증 결과와 한계는 [검증 기록](../docs/semalign-verification.md)에 별도로 기록한다.
