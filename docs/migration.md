# Migration to the src package

2026-10-22에 승인된 구조로 C03 실행 경로를 교체했다.

| 이전 | 현재 |
| --- | --- |
| generate.py / driftlens.py | CLI / runner / environments / observations |
| public_logs.py | contracts.legacy.load_legacy 및 records/v2 검증 |
| sql_tool.py | environments/sql.py |
| 주석뿐인 src/*.py | 실제 src/driftlens_benchmark 패키지 |
| scenarios/A_definition_change | benchmarks/cases/C03_large_orders |
| scenarios/controls | smoke suite의 C03 고정 대조군 |
| data/fixture_orders.csv | datasets/jaffle_shop/fixtures/orders.csv |
| configs/run.example.json | configs/runs/smoke.yaml, configs/agents/sql-agent-v1.yaml |
| 루트 test_*.py | tests/unit, contracts, integration, e2e |

루트 모듈 import와 generate.py 명령은 제거했다. companion은 이미 독립 패키지이며 현재 JSONL 계약을 유지한다. 두 저장소를 같은 부모 폴더에 둘 필요가 없다.

기존 v1 공개 로그는 명시적인 legacy validator로 읽을 수 있다. 예전 네 필드 truth에 없는 참조 결과·검증 상태는 추측해 생성하지 않는다. v2 run을 새로 생성한다.

기존 fixture의 두 주 v1 건수 3/4, v2 건수 1/2를 보존했다. 과거 기본 변경일 2025-01-15와 달리 새 smoke는 월요일인 2025-01-13을 명시한다. 해당 두 주 변경군의 관측은 동일하게 3/2다.

Git 이력·LICENSE, 사용자 환경/원천/기존 runs는 보존했다. 과거 승인 초안의 미리보기 README는 실제 폴더 안내로 대체했다.
