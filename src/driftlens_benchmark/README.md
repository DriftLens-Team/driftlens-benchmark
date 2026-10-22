# driftlens_benchmark

| 구성 | 책임 |
| --- | --- |
| cli.py | validate/run/detect/evaluate 명령과 종료 코드 |
| runner.py | 단계 조립, 변경/고정군 일정, 실패·재현 기록 |
| settings.py | 중복 키 없는 YAML, 버전·경로·자산 checksum |
| artifacts.py | strict JSON, hash, 파일 출력 |
| provenance.py | 패키지·commit·작업 트리·소스 hash |
| [contracts/](contracts/README.md) | agent/v1, records/v2, detection/v1 JSON Schema |
| [environments/](environments/README.md) | CSV/JSONL 적재·snapshot·읽기 전용 SQL |
| [adapters/](adapters/README.md) | 별도 프로세스 JSONL |
| [observations/](observations/README.md) | SQL/답변 검수·private truth·public 추출 |
| [detectors/](detectors/README.md) | SQL 규칙 및 no-drift 기준선 |
| [evaluation/](evaluation/README.md) | 정답 결합·coverage·점수·보고서 |

C03과 agent/v1을 지원한다. SQL 생성·공급자 API·prompt는 외부 agent가 담당한다.
