"""Persistence: SQLite WAL, thread_id, checkpoint history, crash-resume (Phase 2)."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("langgraph.checkpoint.sqlite")

from langgraph_agent_lab.graph import build_graph
from langgraph_agent_lab.persistence import build_checkpointer
from langgraph_agent_lab.state import Route, Scenario, initial_state


def test_sqlite_connection_uses_wal(tmp_path: Path) -> None:
    cp = build_checkpointer("sqlite", str(tmp_path / "wal_evidence.db"))
    assert cp is not None
    try:
        mode = cp.conn.execute("PRAGMA journal_mode").fetchone()
        assert mode is not None
        assert str(mode[0]).upper() == "WAL"
    finally:
        cp.conn.close()


def test_sqlite_thread_id_state_history_and_resume(tmp_path: Path) -> None:
    """thread_id in config, get_state_history after run, new saver+graph resumes same thread."""
    db_path = str(tmp_path / "checkpoint_resume.db")
    scenario = Scenario(
        id="resume-test",
        query="How do I reset my password?",
        expected_route=Route.SIMPLE,
    )
    state0 = initial_state(scenario)
    thread_id = state0["thread_id"]
    config = {"configurable": {"thread_id": thread_id}}

    cp1 = build_checkpointer("sqlite", db_path)
    assert cp1 is not None
    try:
        graph1 = build_graph(cp1)
        final = graph1.invoke(state0, config=config)
        assert final.get("route") == Route.SIMPLE.value

        history = list(graph1.get_state_history(config))
        assert len(history) >= 2
    finally:
        cp1.conn.close()

    cp2 = build_checkpointer("sqlite", db_path)
    assert cp2 is not None
    try:
        graph2 = build_graph(cp2)
        snap = graph2.get_state(config)
        assert snap.values is not None
        assert snap.values.get("thread_id") == thread_id
        assert snap.values.get("route") == Route.SIMPLE.value
        history2 = list(graph2.get_state_history(config))
        assert len(history2) >= 2
    finally:
        cp2.conn.close()
