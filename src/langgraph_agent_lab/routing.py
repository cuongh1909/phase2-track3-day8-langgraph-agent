"""Routing functions for conditional edges."""

from __future__ import annotations

from .state import AgentState, Route


def route_after_classify(state: AgentState) -> str:
    """Map ``state["route"]`` to the first node after classification."""
    route = state.get("route", Route.SIMPLE.value)
    mapping = {
        Route.SIMPLE.value: "answer",
        Route.TOOL.value: "tool",
        Route.MISSING_INFO.value: "clarify",
        Route.RISKY.value: "risky_action",
        Route.ERROR.value: "retry",
    }
    return mapping.get(route, "answer")


def route_after_retry(state: AgentState) -> str:
    """Bounded retry: ``attempt < max_attempts`` → ``tool``, else ``dead_letter``."""
    attempt = int(state.get("attempt", 0))
    max_attempts = int(state.get("max_attempts", 3))
    if attempt >= max_attempts:
        return "dead_letter"
    return "tool"


def route_after_evaluate(state: AgentState) -> str:
    """Retry loop gate: ``needs_retry`` → ``retry``, else ``answer``."""
    if state.get("evaluation_result") == "needs_retry":
        return "retry"
    return "answer"


def route_after_approval(state: AgentState) -> str:
    """Continue to ``tool`` if approved; otherwise ask for clarification."""
    approval = state.get("approval") or {}
    return "tool" if approval.get("approved") else "clarify"
