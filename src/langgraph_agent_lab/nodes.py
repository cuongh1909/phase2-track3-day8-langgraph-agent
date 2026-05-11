"""Node skeletons for the LangGraph workflow.

Each function should be small, testable, and return a partial state update. Avoid mutating the
input state in place.
"""

from __future__ import annotations

import re

from .state import AgentState, ApprovalDecision, Route, make_event

_PUNCT_STRIP = "?!.,;:\"'()[]"

# Classify: risky → tool → missing_info → error → simple (README order).
_RISKY_TERMS = ("refund", "delete", "send", "cancel", "remove", "revoke")
_TOOL_TERMS = ("status", "order", "lookup", "check", "track", "find", "search")
_ERROR_TERMS = ("timeout", "fail", "failure", "error", "crash", "unavailable")
_VAGUE_PRONOUNS = frozenset({"it", "this", "that", "them", "something", "anything", "someone"})


def _word_tokens(query: str) -> list[str]:
    return [w.strip(_PUNCT_STRIP).lower() for w in query.split() if w.strip(_PUNCT_STRIP)]


def _has_whole_word(text_lower: str, terms: tuple[str, ...]) -> bool:
    return any(re.search(rf"\b{re.escape(t)}\b", text_lower) for t in terms)


def _is_missing_info(query_lower: str, tokens: list[str]) -> bool:
    if len(tokens) >= 5:
        return False
    return bool(_VAGUE_PRONOUNS.intersection(tokens))


def intake_node(state: AgentState) -> dict:
    """Normalize raw query into state fields.

    TODO(student): add normalization, PII checks, and metadata extraction.
    """
    query = state.get("query", "").strip()
    return {
        "query": query,
        "messages": [f"intake:{query[:40]}"],
        "events": [make_event("intake", "completed", "query normalized")],
    }


def classify_node(state: AgentState) -> dict:
    """Classify the query into a route using keyword heuristics (README table).

    Priority: risky → tool → missing_info → error → simple.
    """
    query_raw = state.get("query", "")
    query = query_raw.lower()
    tokens = _word_tokens(query_raw)
    risk_level = "low"
    route = Route.SIMPLE

    if _has_whole_word(query, _RISKY_TERMS):
        route = Route.RISKY
        risk_level = "high"
    elif _has_whole_word(query, _TOOL_TERMS):
        route = Route.TOOL
    elif _is_missing_info(query, tokens):
        route = Route.MISSING_INFO
    elif _has_whole_word(query, _ERROR_TERMS):
        route = Route.ERROR

    return {
        "route": route.value,
        "risk_level": risk_level,
        "events": [make_event("classify", "completed", f"route={route.value}")],
    }


def ask_clarification_node(state: AgentState) -> dict:
    """Ask for missing information instead of hallucinating.

    TODO(student): generate a specific clarification question from state.
    """
    question = "Can you provide the order id or the missing context?"
    return {
        "pending_question": question,
        "final_answer": question,
        "events": [make_event("clarify", "completed", "missing information requested")],
    }


def tool_node(state: AgentState) -> dict:
    """Call a mock tool.

    Simulates transient failures when ``route`` is ``error``, ``should_retry`` is true,
    and there is still retry budget (``attempt < max_attempts - 1`` after ``retry`` bump).
    """
    attempt = int(state.get("attempt", 0))
    max_attempts = int(state.get("max_attempts", 3))
    route = state.get("route", "")
    should_retry = bool(state.get("should_retry", False))

    transient = (
        route == Route.ERROR.value
        and should_retry
        and attempt > 0
        and attempt < max_attempts - 1
    )
    if transient:
        sid = state.get("scenario_id", "unknown")
        result = f"ERROR: transient failure attempt={attempt} scenario={sid}"
    else:
        result = f"mock-tool-result for scenario={state.get('scenario_id', 'unknown')}"
    return {
        "tool_results": [result],
        "events": [make_event("tool", "completed", f"tool executed attempt={attempt}")],
    }


def risky_action_node(state: AgentState) -> dict:
    """Prepare a risky action for approval.

    TODO(student): create a proposed action with evidence and risk justification.
    """
    return {
        "proposed_action": "prepare refund or external action; approval required",
        "events": [make_event("risky_action", "pending_approval", "approval required")],
    }


def approval_node(state: AgentState) -> dict:
    """Human approval step with optional LangGraph interrupt().

    Set LANGGRAPH_INTERRUPT=true to use real interrupt() for HITL demos.
    Default uses mock decision so tests and CI run offline.

    TODO(student): implement reject/edit decisions and timeout escalation.
    """
    import os

    if os.getenv("LANGGRAPH_INTERRUPT", "").lower() == "true":
        from langgraph.types import interrupt

        value = interrupt({
            "proposed_action": state.get("proposed_action"),
            "risk_level": state.get("risk_level"),
        })
        if isinstance(value, dict):
            decision = ApprovalDecision(**value)
        else:
            decision = ApprovalDecision(approved=bool(value))
    else:
        decision = ApprovalDecision(approved=True, comment="mock approval for lab")
    return {
        "approval": decision.model_dump(),
        "events": [make_event("approval", "completed", f"approved={decision.approved}")],
    }


def retry_or_fallback_node(state: AgentState) -> dict:
    """Record a retry attempt or fallback decision.

    TODO(student): implement bounded retry, exponential backoff metadata, and fallback route.
    """
    attempt = int(state.get("attempt", 0)) + 1
    errors = [f"transient failure attempt={attempt}"]
    return {
        "attempt": attempt,
        "errors": errors,
        "events": [make_event("retry", "completed", "retry attempt recorded", attempt=attempt)],
    }


def answer_node(state: AgentState) -> dict:
    """Produce a final response.

    TODO(student): ground the answer in tool_results and approval where relevant.
    """
    if state.get("tool_results"):
        answer = f"I found: {state['tool_results'][-1]}"
    else:
        answer = "This is a safe mock answer. Replace with your agent response."
    return {
        "final_answer": answer,
        "events": [make_event("answer", "completed", "answer generated")],
    }


def evaluate_node(state: AgentState) -> dict:
    """Evaluate tool results — gate for the retry loop via ``evaluation_result``."""
    tool_results = state.get("tool_results", [])
    latest = tool_results[-1] if tool_results else ""
    if "ERROR" in latest.upper():
        return {
            "evaluation_result": "needs_retry",
            "events": [
                make_event("evaluate", "completed", "tool result indicates failure, retry needed"),
            ],
        }
    return {
        "evaluation_result": "success",
        "events": [make_event("evaluate", "completed", "tool result satisfactory")],
    }


def dead_letter_node(state: AgentState) -> dict:
    """Log unresolvable failures when retry budget is exhausted (manual review / DLQ)."""
    sid = state.get("scenario_id", "unknown")
    attempt = int(state.get("attempt", 0))
    max_attempts = int(state.get("max_attempts", 3))
    msg = (
        f"dead_letter: scenario={sid} attempt={attempt} max_attempts={max_attempts} "
        "(exhausted retries; escalate to human)"
    )
    dl_msg = (
        "Request could not be completed after maximum retry attempts. "
        "Logged for manual review."
    )
    return {
        "final_answer": dl_msg,
        "errors": [msg],
        "events": [
            make_event("dead_letter", "completed", f"max retries exceeded, attempt={attempt}"),
        ],
    }


def finalize_node(state: AgentState) -> dict:
    """Finalize the run and emit a final audit event."""
    return {"events": [make_event("finalize", "completed", "workflow finished")]}
