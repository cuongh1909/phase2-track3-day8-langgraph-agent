"""CLI for the lab."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer
import yaml

from .graph import build_graph
from .metrics import MetricsReport, metric_from_state, summarize_metrics, write_metrics
from .persistence import build_checkpointer
from .report import write_report
from .scenarios import load_scenarios
from .state import initial_state

app = typer.Typer(no_args_is_help=True)


@app.command("run-scenarios")
def run_scenarios(
    config: Annotated[Path, typer.Option("--config")],
    output: Annotated[Path, typer.Option("--output")],
) -> None:
    """Run all grading scenarios and write metrics JSON."""
    cfg = yaml.safe_load(config.read_text(encoding="utf-8"))
    scenarios = load_scenarios(cfg["scenarios_path"])
    checkpointer = build_checkpointer(cfg.get("checkpointer", "memory"), cfg.get("database_url"))
    graph = build_graph(checkpointer=checkpointer)
    metrics = []
    for scenario in scenarios:
        state = initial_state(scenario)
        run_config = {"configurable": {"thread_id": state["thread_id"]}}
        final_state = graph.invoke(state, config=run_config)
        metrics.append(metric_from_state(final_state, scenario.expected_route.value, scenario.requires_approval))
    report = summarize_metrics(metrics)
    write_metrics(report, output)
    if cfg.get("report_path"):
        write_report(report, cfg["report_path"])
    typer.echo(f"Wrote metrics to {output}")


@app.command("export-mermaid")
def export_mermaid(
    output: Annotated[Path, typer.Option("--output", help="Path for .mmd file")] = Path(
        "outputs/graph.mmd",
    ),
) -> None:
    """Phase 4 bonus: export the main workflow as Mermaid (``draw_mermaid()``)."""
    from .bonus_extensions import export_main_workflow_mermaid

    text = export_main_workflow_mermaid()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(text, encoding="utf-8")
    typer.echo(f"Wrote Mermaid diagram to {output}")


@app.command("demo-parallel-fanout")
def demo_parallel_fanout(
    query: Annotated[str, typer.Option("--query", help="Sample query stored in demo state")] = (
        "lookup order 12345"
    ),
) -> None:
    """Phase 4 bonus: run a tiny graph with ``Send()`` fan-out; merged ``tool_results``."""
    from .bonus_extensions import run_parallel_fanout_demo

    result = run_parallel_fanout_demo(query)
    typer.echo(str(dict(result)))


@app.command("demo-time-travel")
def demo_time_travel(
    sqlite_db: Annotated[
        Path | None,
        typer.Option("--sqlite-db", help="Optional SQLite DB path (uses memory if omitted)"),
    ] = None,
) -> None:
    """Phase 4 bonus: print ``get_state_history`` and one ``get_state`` rewind."""
    from .bonus_extensions import time_travel_demo_lines

    path = str(sqlite_db) if sqlite_db else None
    for line in time_travel_demo_lines(use_sqlite_path=path):
        typer.echo(line)


@app.command("demo-crash-recovery")
def demo_crash_recovery(
    sqlite_db: Annotated[
        Path,
        typer.Option("--sqlite-db", help="SQLite file path (created if missing)"),
    ] = Path("outputs/crash_recovery_demo.db"),
) -> None:
    """Phase 4 bonus: close SQLite conn then reopen; checkpoints survive."""
    from .bonus_extensions import sqlite_crash_recovery_demo_lines

    for line in sqlite_crash_recovery_demo_lines(str(sqlite_db)):
        typer.echo(line)


@app.command("validate-metrics")
def validate_metrics(metrics: Annotated[Path, typer.Option("--metrics")]) -> None:
    """Validate metrics JSON schema for grading."""
    payload = json.loads(metrics.read_text(encoding="utf-8"))
    report = MetricsReport.model_validate(payload)
    if report.total_scenarios < 6:
        raise typer.BadParameter("Expected at least 6 scenarios")
    typer.echo(f"Metrics valid. success_rate={report.success_rate:.2%}")


if __name__ == "__main__":
    app()
