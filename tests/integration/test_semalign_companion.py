"""Opt-in real v2 CLI test; no companion internals or live provider calls."""

import os

import pytest
from fixtures.semalign_evaluation import create_evaluation_source

from driftlens_benchmark.semalign_runner import run_semalign


@pytest.mark.semalign_companion
def test_real_v2_companion_all_metrics_and_profiles(tmp_path):
    python = os.environ.get("DRIFTLENS_SEMALIGN_AGENT_PYTHON")
    if not python:
        pytest.skip("Set DRIFTLENS_SEMALIGN_AGENT_PYTHON to an installed agent/v2 Python")
    source = create_evaluation_source(tmp_path / "source")
    result = run_semalign(source, tmp_path / "run", mode="agent", agent_python=python, provider="fake")
    assert result["status"] == "complete"
    assert result["validated"] == 56
    assert result["complete_series"] == 7
    assert result["model_execution"] == "deterministic_fake"
