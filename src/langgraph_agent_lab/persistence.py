"""Checkpointer adapter."""

from __future__ import annotations

import sqlite3

from langgraph.checkpoint.base import BaseCheckpointSaver


def _open_sqlite_connection(db_path: str) -> sqlite3.Connection:
    """Open SQLite for LangGraph checkpoints with WAL durability (README Phase 2)."""
    conn = sqlite3.connect(db_path, check_same_thread=False)
    # WAL: better crash-safety and concurrent readers while the graph writes checkpoints.
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.commit()
    return conn


def build_checkpointer(
    kind: str = "memory",
    database_url: str | None = None,
) -> BaseCheckpointSaver | None:
    """Return a LangGraph checkpointer.

    - ``memory``: in-process ``MemorySaver()`` (dev default).
    - ``sqlite``: ``SqliteSaver(conn=sqlite3.connect(...))`` with WAL enabled on the
      connection (see README — avoid ``from_conn_string`` as the sole return value; it is
      a context manager).
    - ``postgres``: not built here (``PostgresSaver.from_conn_string`` is a context manager);
      use that API directly if you need Postgres checkpoints.
    """
    if kind == "none":
        return None
    if kind == "memory":
        from langgraph.checkpoint.memory import MemorySaver

        return MemorySaver()
    if kind == "sqlite":
        try:
            from langgraph.checkpoint.sqlite import SqliteSaver
        except ImportError as exc:
            msg = "SQLite checkpointer requires: pip install langgraph-checkpoint-sqlite"
            raise RuntimeError(msg) from exc
        db_path = database_url or "checkpoints.db"
        conn = _open_sqlite_connection(db_path)
        return SqliteSaver(conn)
    if kind == "postgres":
        raise RuntimeError(
            "Postgres is not constructed here: PostgresSaver.from_conn_string() is a "
            "context manager. Use `with PostgresSaver.from_conn_string(url) as saver:` in "
            "your app, or use checkpointer kind 'memory' / 'sqlite' for this lab."
        )
    raise ValueError(f"Unknown checkpointer kind: {kind}")
