# Day 08 Lab Report

## 1. Team / student

- Name: *(fill for submission)*
- Repo/commit: *(fill for submission)*
- Date: *(fill for submission)*

## 2. Architecture

The workflow is a **LangGraph** `StateGraph` compiled with an optional checkpointer (`configs/lab.yaml`).

**Linear entry:** `START` → `intake` (normalize query) → `classify` (keyword routing).

**Conditional routing from `classify`:**
| Route | Next nodes (summary) |
|------|------------------------|
| `simple` | `answer` → `finalize` → `END` |
| `tool` | `tool` → `evaluate` → `answer` → `finalize` → `END` |
| `missing_info` | `clarify` → `finalize` → `END` |
| `risky` | `risky_action` → `approval` → `tool` → `evaluate` → `answer` → `finalize` → `END` |
| `error` | `retry` → `tool` → `evaluate` → (`retry` loop **or** `answer`) → `finalize` → `END` |
| (retry budget exhausted) | `dead_letter` → `finalize` → `END` |

**Retry loop:** `evaluate_node` sets `evaluation_result` to `needs_retry` or `success`. `route_after_evaluate` sends `needs_retry` to `retry` (increments `attempt`); `route_after_retry` sends to `tool` while `attempt < max_attempts`, else `dead_letter`.

**Human-in-the-loop:** `approval_node` records an `approval` dict (mock `approved=True` unless `LANGGRAPH_INTERRUPT=true`).

## 3. State schema

| Field | Reducer / behavior | Role |
|------|---------------------|------|
| `messages`, `tool_results`, `errors`, `events` | append (`Annotated[list, add]`) | audit, tool output, failures, node events |
| `thread_id`, `scenario_id`, `query` | overwrite | run identity and input |
| `route`, `risk_level` | overwrite | classifier output |
| `attempt`, `max_attempts`, `should_retry` | overwrite | retry policy from scenario + runtime |
| `evaluation_result` | overwrite | gate between `evaluate` and `retry` / `answer` |
| `final_answer`, `pending_question`, `proposed_action` | overwrite | user-facing outputs |
| `approval` | overwrite | HITL decision payload |

## 4. Scenario results

Aggregates from this metrics run (see also `outputs/metrics.json`):

- **Total scenarios:** 7
- **Success rate:** 100.00%
- **Average nodes visited:** 6.57
- **Total retries** (visits to `retry` node): 4
- **Total interrupts** (visits to `approval` node): 2

Per-scenario table:

| Scenario | Expected route | Actual route | Success | Retries | Interrupts | Approval seen | Errors (truncated) |
|---|---|---|---:|---:|---:|---|---|
| S01_simple | simple | simple | yes | 0 | 0 | no | — |
| S02_tool | tool | tool | yes | 0 | 0 | no | — |
| S03_missing | missing_info | missing_info | yes | 0 | 0 | no | — |
| S04_risky | risky | risky | yes | 0 | 1 | yes | — |
| S05_error | error | error | yes | 3 | 0 | no | transient failure attempt=1; transient failure attempt=2; transient failure attempt=3; de… |
| S06_delete | risky | risky | yes | 0 | 1 | yes | — |
| S07_dead_letter | error | error | yes | 1 | 0 | no | transient failure attempt=1; dead_letter: scenario=S07_dead_letter attempt=1 max_attempts… |

## 5. Failure analysis

1. **Transient tool / retry path:** For `error` + `should_retry`, `tool_node` may return a synthetic `ERROR:` result. `evaluate_node` marks `needs_retry`; `retry_node` bumps `attempt` and bounded routing prevents infinite loops. **S07** uses `max_attempts: 1` so the graph reaches `dead_letter` immediately after the first retry accounting step—**expected** for the dead-letter scenario. Residual risk: keyword overlap could mis-route (mitigated by strict keyword priority in `classify_node`).

2. **Risky actions without approval:** The `risky` path always enters `approval` before `tool`. Metrics require `approval_observed` when `requires_approval` is true; mock approval approves by default. **Failure mode if rejected:** `route_after_approval` routes to `clarify` instead of `tool`—user gets a clarification-style response rather than a silent execution.

3. **Metrics false negatives:** Success requires `actual_route == expected_route` and a non-empty `final_answer` or `pending_question`. Empty answers or route drift would show as failures in `outputs/metrics.json`.

All sample scenarios passed (`success_rate` = 100%). Hidden grading scenarios may still surface edge cases in keyword routing or retries.

## 6. Persistence / recovery evidence

- **Default lab run:** `checkpointer: memory` in `configs/lab.yaml` — `MemorySaver()`; each scenario uses `thread_id` from `initial_state` (prefix `thread-` plus scenario id) and passes `config` with `configurable.thread_id` into `graph.invoke`.
- **SQLite extension:** `build_checkpointer("sqlite", database_url)` opens `sqlite3.connect(..., check_same_thread=False)`, sets **WAL** (`PRAGMA journal_mode=WAL`), and returns `SqliteSaver(conn)` (see `persistence.py`). Tests in `tests/test_persistence.py` assert WAL mode, non-empty `get_state_history`, and **resume** via a new connection on the same DB file.

## 7. Extension work

- SQLite checkpoint saver + WAL + automated persistence tests (Phase 2).
- **Phase 4 bonuses (see `bonus_extensions.py` + Makefile):** `make bonus-mermaid` writes `outputs/graph.mmd` via `draw_mermaid()`; `make bonus-parallel` runs a separate `Send()` fan-out graph with `tool_results` merged by `add`; `make bonus-time-travel` prints `get_state_history` plus one `get_state` rewind using a stored `checkpoint_id`; `make bonus-crash-recovery` closes SQLite then reopens the same DB file and reads state (simulated crash + restart).
- **Real HITL:** set `LANGGRAPH_INTERRUPT=true` (see `.env.example`); `approval_node` calls LangGraph `interrupt()` and resumes with a dict payload shaped like `ApprovalDecision` (or use `graph.update_state` / LangGraph Cloud UI depending on your runtime).
- **Not implemented here:** Streamlit approval UI (would wrap `interrupt`/`Command` resume); use LangGraph Studio or a small custom client if you need a browser surface.

## 8. Improvement plan

1. Replace keyword `classify_node` with a small classifier model or LLM call with structured output, still validated against policy rules.
2. Structured tool results (JSON schema) instead of string `ERROR:` heuristics in `evaluate_node`.
3. Production SQLite lifecycle: connection pooling or lifecycle hooks to close `conn` on shutdown; optional `SqliteSaver.setup()` timing documented.
4. Richer metrics: latency per node from `events`, explicit `dead_letter` flag in final state.