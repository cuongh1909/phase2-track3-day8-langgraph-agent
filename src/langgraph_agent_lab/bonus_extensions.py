"""Phase 4 bonus: Mermaid export, Send() parallel fan-out demo, time-travel inspection.

These live beside the main grading graph so scenario runs stay keyword-driven and unchanged.
"""

from __future__ import annotations

import importlib.util
from operator import add
from typing import Annotated

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Send
from typing_extensions import TypedDict

from .graph import build_graph
from .persistence import build_checkpointer
from .state import Route, Scenario, initial_state


def export_main_workflow_mermaid() -> str:
    """Return a Mermaid diagram for the support-ticket workflow graph."""
    graph = build_graph(checkpointer=None)
    return graph.get_graph().draw_mermaid()


class _ParallelDemoState(TypedDict, total=False):
    """Minimal state: two mock tools append into ``tool_results``."""

    tool_results: Annotated[list[str], add]
    query: str


def _parallel_gate(state: _ParallelDemoState) -> list[Send]:
    return [Send("mock_inventory", state), Send("mock_billing", state)]


def _mock_inventory(state: _ParallelDemoState) -> dict:
    q = (state.get("query") or "")[:24]
    return {"tool_results": [f"parallel:inventory:{q!r}"]}


def _mock_billing(state: _ParallelDemoState) -> dict:
    return {"tool_results": ["parallel:billing:ok"]}


def _parallel_join(_: _ParallelDemoState) -> dict:
    return {}


def build_parallel_fanout_demo_graph() -> CompiledStateGraph:
    """Two-node fan-out from ``START`` via ``Send()``; results merge with ``operator.add``."""
    g: StateGraph = StateGraph(_ParallelDemoState)
    g.add_node("mock_inventory", _mock_inventory)
    g.add_node("mock_billing", _mock_billing)
    g.add_node("join", _parallel_join)
    g.add_conditional_edges(START, _parallel_gate)
    g.add_edge("mock_inventory", "join")
    g.add_edge("mock_billing", "join")
    g.add_edge("join", END)
    return g.compile()


def run_parallel_fanout_demo(query: str = "lookup order 12345") -> dict[str, object]:
    app = build_parallel_fanout_demo_graph()
    return app.invoke({"query": query, "tool_results": []})


def time_travel_demo_lines(
    *,
    query: str = "Please lookup order status for order 12345",
    scenario_id: str = "bonus-tt",
    use_sqlite_path: str | None = None,
) -> list[str]:
    """Log lines: checkpoint history summary + one ``get_state`` rewind by ``checkpoint_id``."""
    if use_sqlite_path:
        cp = build_checkpointer("sqlite", use_sqlite_path)
    else:
        cp = build_checkpointer("memory")
    graph = build_graph(checkpointer=cp)
    scenario = Scenario(id=scenario_id, query=query, expected_route=Route.TOOL)
    st0 = initial_state(scenario)
    cfg = {"configurable": {"thread_id": st0["thread_id"]}}
    graph.invoke(st0, config=cfg)

    history = list(graph.get_state_history(cfg))
    lines: list[str] = [
        f"checkpoints_in_history={len(history)}",
    ]
    for i, snap in enumerate(history):
        cid = snap.config.get("configurable", {}).get("checkpoint_id", "")
        nxt = ",".join(snap.next) if snap.next else ""
        route = (snap.values or {}).get("route", "")
        lines.append(f"  [{i}] checkpoint_id={cid[:8]}... next=({nxt}) route={route!r}")

    if len(history) >= 3:
        mid = history[len(history) // 2]
        cid = mid.config["configurable"]["checkpoint_id"]
        cfg_past = {"configurable": {**cfg["configurable"], "checkpoint_id": cid}}
        past = graph.get_state(cfg_past)
        lines.append(
            "rewind: get_state(config with historical checkpoint_id) -> "
            f"route={past.values.get('route')!r} next={past.next}"
        )

    if cp is not None and hasattr(cp, "conn"):
        cp.conn.close()
    return lines


def sqlite_crash_recovery_demo_lines(db_path: str) -> list[str]:
    """Simulate process exit (connection closed) then a new process reopening the same DB.

    Uses the same SQLite file and ``thread_id``; second graph reads checkpoints written
    before ``conn.close()`` — analogous to survive ``kill -9`` + restart for this lab.
    """
    if importlib.util.find_spec("langgraph.checkpoint.sqlite") is None:
        raise RuntimeError("Install langgraph-checkpoint-sqlite for this demo")

    scenario = Scenario(
        id="crash-demo",
        query="How do I reset my password?",
        expected_route=Route.SIMPLE,
    )
    st0 = initial_state(scenario)
    cfg = {"configurable": {"thread_id": st0["thread_id"]}}

    cp1 = build_checkpointer("sqlite", db_path)
    g1 = build_graph(checkpointer=cp1)
    out1 = g1.invoke(st0, config=cfg)
    cp1.conn.close()

    cp2 = build_checkpointer("sqlite", db_path)
    g2 = build_graph(checkpointer=cp2)
    snap = g2.get_state(cfg)
    cp2.conn.close()

    lines = [
        "sqlite_crash_recovery_demo: closed first SqliteSaver connection (simulated crash exit)",
        f"first_invoke_final_route={out1.get('route')!r}",
        f"reopen_same_file_get_state_route={(snap.values or {}).get('route')!r}",
        f"thread_id={st0['thread_id']!r}",
    ]
    if (snap.values or {}).get("route") != out1.get("route"):
        lines.append("WARNING: route mismatch after reopen (unexpected)")
    return lines
