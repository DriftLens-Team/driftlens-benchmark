import sys

import pytest

from driftlens_benchmark.adapters.jsonl import AgentFailure, exchange
from driftlens_benchmark.artifacts import write_json
from driftlens_benchmark.environments.build import load_orders, snapshot
from driftlens_benchmark.runner import agent_config
from driftlens_benchmark.settings import load_suite

REQUEST = {
    "request_id": "req-1",
    "request": "이번 주 대형 주문은 몇 건인가요?",
    "period": "2025-W02",
    "timestamp": "2025-01-12T23:59:59Z",
}


@pytest.fixture
def command(root, tmp_path):
    suite = load_suite(root / "benchmarks/suites/smoke.yaml")
    db = tmp_path / "db.sqlite"
    snapshot(load_orders(suite.orders), suite.schema, db, "2025-01-13")
    runtime = agent_config(db, {"provider": "fake", "model_id_env": "MODEL", "api_key_env": "KEY"})
    write_json(tmp_path / "config.json", runtime)
    write_json(tmp_path / "profile.json", suite.definitions["v1"])

    def make(mode):
        return [
            sys.executable,
            str(root / "tests/fixtures/protocol_agent.py"),
            "--mode",
            mode,
            "--config",
            str(tmp_path / "config.json"),
            "--profile",
            str(tmp_path / "profile.json"),
        ]

    return make


def test_normal_process(command, tmp_path):
    observation, diagnostic = exchange(command("normal"), REQUEST, cwd=tmp_path, timeout=3)
    assert observation["reported_values"][0]["value"] == 3
    assert diagnostic["exit_code"] == 0


@pytest.mark.parametrize(
    "mode,code",
    [
        ("malformed", "invalid_agent_response"),
        ("duplicate", "invalid_agent_response"),
        ("wrong_id", "invalid_agent_response"),
        ("oversize", "response_too_large"),
        ("nonzero", "agent_exit_failed"),
        ("error", "unsupported_request"),
        ("hang", "agent_timeout"),
    ],
)
def test_process_failures_never_observations(command, tmp_path, mode, code):
    with pytest.raises(AgentFailure) as error:
        exchange(command(mode), REQUEST, cwd=tmp_path, timeout=0.4 if mode == "hang" else 3)
    assert error.value.code == code


def test_no_internal_agent_imports(root):
    # A textual occurrence in the process command is allowed; an import is not.
    import ast

    for path in (root / "src/driftlens_benchmark").rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ImportFrom):
                assert not (node.module or "").startswith("driftlens_sql_agent")
            if isinstance(node, ast.Import):
                assert not any(n.name.startswith("driftlens_sql_agent") for n in node.names)
