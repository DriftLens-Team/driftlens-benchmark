from pathlib import Path

import pytest
import yaml

from driftlens_benchmark.runner import run

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def root():
    return ROOT


@pytest.fixture
def run_config(tmp_path):
    def create(mode="normal"):
        agent = {
            "version": 1,
            "protocol": "agent/v1",
            "command": ["{python}", str(ROOT / "tests" / "fixtures" / "protocol_agent.py"), "--mode", mode],
            "provider": "fake",
            "timeout_seconds": 3,
            "capabilities": ["large_orders", "weekly", "orders-v1"],
            "model_id_env": "UPSTAGE_MODEL",
            "api_key_env": "UPSTAGE_API_KEY",
        }
        agent_path = tmp_path / f"agent-{mode}.yaml"
        agent_path.write_text(yaml.safe_dump(agent), encoding="utf-8")
        config = {
            "version": 1,
            "suite": str(ROOT / "benchmarks" / "suites" / "smoke.yaml"),
            "agent": str(agent_path),
            "seed": 17,
        }
        path = tmp_path / f"run-{mode}.yaml"
        path.write_text(yaml.safe_dump(config), encoding="utf-8")
        return path

    return create


@pytest.fixture
def completed_run(tmp_path, run_config):
    output = tmp_path / "complete"
    run(run_config(), output)
    return output
