# Migration to the src package

C03 실행은 `python -m driftlens_benchmark` CLI를 사용한다.

| 이전 | 현재 |
| --- | --- |
| generate.py / driftlens.py | CLI / runner / environments / observations |
| public_logs.py | contracts.legacy.load_legacy 및 records/v2 검증 |
| sql_tool.py | environments/sql.py |
| scenarios/A_definition_change | benchmarks/cases/C03_large_orders |
| scenarios/controls | smoke suite의 C03 고정 대조군 |
| data/fixture_orders.csv | datasets/jaffle_shop/fixtures/orders.csv |
| configs/run.example.json | configs/runs/smoke.yaml, configs/agents/sql-agent-v1.yaml |
| 루트 test_*.py | tests/unit, contracts, integration, e2e |

루트 모듈 import와 generate.py 명령은 제거했다. companion은 이미 독립 패키지이며 현재 JSONL 계약을 유지한다. 두 저장소를 같은 부모 폴더에 둘 필요가 없다.

기존 v1 공개 로그는 명시적인 legacy validator로 읽을 수 있다. 예전 네 필드 truth에 없는 참조 결과·검증 상태는 추측해 생성하지 않는다. v2 run을 새로 생성한다.

smoke의 기본 변경일은 2025-01-15에서 2025-01-13으로 바뀌었다. 두 주 변경군의 관측은 3/2로 동일하다.
