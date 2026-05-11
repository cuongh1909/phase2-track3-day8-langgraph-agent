"""Phase 4 bonus extensions (Mermaid, Send fan-out, time-travel, crash-recovery demo)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from langgraph_agent_lab.bonus_extensions import (
    export_main_workflow_mermaid,
    run_parallel_fanout_demo,
    sqlite_crash_recovery_demo_lines,
    time_travel_demo_lines,
)


def test_export_mermaid_contains_core_nodes() -> None:
    mermaid = export_main_workflow_mermaid()
    for needle in ("intake", "classify", "finalize", "graph TD"):
        assert needle in mermaid


def test_parallel_fanout_merges_tool_results() -> None:
    out = run_parallel_fanout_demo("lookup order 99")
    assert len(out["tool_results"]) == 2
    joined = " ".join(out["tool_results"])
    assert "parallel:inventory" in joined
    assert "parallel:billing" in joined


def test_time_travel_history_and_rewind() -> None:
    lines = time_travel_demo_lines()
    text = "\n".join(lines)
    assert "checkpoints_in_history=" in text
    assert "rewind:" in text


@pytest.mark.skipif(
    importlib.util.find_spec("langgraph.checkpoint.sqlite") is None,
    reason="langgraph-checkpoint-sqlite not installed",
)
def test_sqlite_crash_recovery_demo(tmp_path: Path) -> None:
    db = str(tmp_path / "crash.db")
    lines = sqlite_crash_recovery_demo_lines(db)
    text = "\n".join(lines)
    assert "reopen_same_file_get_state_route=" in text
    assert "WARNING" not in text
