#!/usr/bin/env python3
"""
Minimal MCP server (Python) that exposes a database as tools you can call from your MCP‑capable client
(e.g., Claude Desktop). Defaults to SQLite but works with any SQLAlchemy-supported DB via DATABASE_URL.

Tools provided
--------------
- list_tables() -> list[str]
- describe_table(table: str) -> dict
- query(sql: str, params_json: str | None = None, limit: int = 1000, dry_run: bool = False) -> dict
  * By default the server is READ-ONLY (SELECT/CTE).
  * Set ALLOW_WRITE=true to permit INSERT/UPDATE/DELETE/etc.

Environment variables
---------------------
- DATABASE_URL: e.g.,
    sqlite:///./example.db
    postgresql+psycopg://user:pass@localhost:5432/mydb
    mysql+pymysql://user:pass@localhost:3306/mydb
- ALLOW_WRITE: "true" to allow non-SELECT statements (default: false)
- QUERY_TIMEOUT_SECS: statement timeout in seconds (default: 30)

Install
-------
    pip install mcp sqlalchemy aiosqlite psycopg[binary] pymysql

Claude Desktop config (example)
-------------------------------
Add this under "mcpServers" in your claude_desktop_config.json:

    "db": {
      "command": "python",
      "args": ["/ABS/PATH/TO/db_mcp_server.py"],
      "env": {
        "DATABASE_URL": "sqlite:///./example.db",
        "ALLOW_WRITE": "false"
      }
    }

Then (re)launch your client and connect to the "db" MCP server. Ask it to run db.query, db.list_tables, etc.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
from typing import Any, Dict, List

from mcp.server.fastmcp import FastMCP  # type: ignore
from mcp.types import Tool, TextContent, ImageContent  # noqa: F401  (kept for reference)

from sqlalchemy import create_engine, text, inspect
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

APP_NAME = "db"
mcp = FastMCP(APP_NAME)

# --- DB setup -----------------------------------------------------------------

def _make_engine() -> Engine:
    dsn = os.environ.get("DATABASE_URL", "sqlite:///./example.db")
    # SQLite with check_same_thread=False for simple concurrency in MCP handlers
    connect_args = {"check_same_thread": False} if dsn.startswith("sqlite") else {}
    return create_engine(dsn, pool_pre_ping=True, connect_args=connect_args)

ENGINE = _make_engine()
ALLOW_WRITE = os.environ.get("ALLOW_WRITE", "false").lower() in {"1", "true", "yes", "y"}
QUERY_TIMEOUT_SECS = int(os.environ.get("QUERY_TIMEOUT_SECS", "30"))

READONLY_OK_PREFIXES = (
    "select",
    "with",  # CTEs
    "pragma",  # helpful for sqlite schema inspection
    "show",    # MySQL
    "describe" # MySQL
)

# --- Utilities ----------------------------------------------------------------

def _enforce_readonly(sql: str) -> None:
    if ALLOW_WRITE:
        return
    first_token = re.split(r"\s+", sql.strip(), maxsplit=1)[0].lower()
    if not first_token.startswith(READONLY_OK_PREFIXES):
        raise PermissionError(
            "Write statements are disabled. Set ALLOW_WRITE=true to enable non-SELECT SQL."
        )


def _limit_sql(sql: str, limit: int) -> str:
    # Naive limiter for common dialects when user forgets a LIMIT/Top clause
    s = sql.strip().rstrip(";")
    if re.search(r"\blimit\b", s, flags=re.IGNORECASE):
        return s
    # Append LIMIT for SQLite/Postgres/MySQL; for MSSQL you'd use TOP in the SELECT
    return f"{s} LIMIT {limit}"


# --- Tools --------------------------------------------------------------------

@mcp.tool()
def list_tables() -> List[str]:
    """Return a list of table names in the connected database."""
    insp = inspect(ENGINE)
    try:
        names = sorted(set(insp.get_table_names()) | set(insp.get_view_names()))
        return names
    finally:
        insp._dispose()  # type: ignore[attr-defined]


@mcp.tool()
def describe_table(table: str) -> Dict[str, Any]:
    """Describe columns for a given table (name, type, nullable, default)."""
    insp = inspect(ENGINE)
    try:
        cols = insp.get_columns(table)
        pks = insp.get_pk_constraint(table) or {}
        fks = insp.get_foreign_keys(table) or []
        return {
            "table": table,
            "columns": [
                {
                    "name": c.get("name"),
                    "type": str(c.get("type")),
                    "nullable": bool(c.get("nullable", True)),
                    "default": c.get("default"),
                }
                for c in cols
            ],
            "primary_key": pks.get("constrained_columns", []),
            "foreign_keys": [
                {
                    "constrained_columns": fk.get("constrained_columns"),
                    "referred_schema": fk.get("referred_schema"),
                    "referred_table": fk.get("referred_table"),
                    "referred_columns": fk.get("referred_columns"),
                }
                for fk in fks
            ],
        }
    finally:
        insp._dispose()  # type: ignore[attr-defined]


@mcp.tool()
def query(sql: str, params_json: str | None = None, limit: int = 1000, dry_run: bool = False) -> Dict[str, Any]:
    """Execute a SQL query safely.

    Args:
        sql: SQL text. When ALLOW_WRITE is false, only SELECT/CTE/etc. are allowed.
        params_json: Optional JSON mapping of bind parameters, e.g. '{"id": 123}'.
        limit: If no LIMIT/TOP present, add LIMIT automatically (SQLite/Postgres/MySQL).
        dry_run: If true, validate and return the would-be SQL without executing.
    Returns:
        dict with keys: {"sql", "rowcount", "columns", "rows"}
    """
    _enforce_readonly(sql)

    try:
        params = json.loads(params_json) if params_json else {}
    except json.JSONDecodeError as e:
        raise ValueError(f"params_json is not valid JSON: {e}")

    final_sql = _limit_sql(sql, limit)

    if dry_run:
        return {"sql": final_sql, "rowcount": 0, "columns": [], "rows": []}

    try:
        with ENGINE.connect() as conn:
            # Apply per-statement timeout if supported by the backend
            if conn.dialect.name == "sqlite":
                conn.exec_driver_sql(f"PRAGMA busy_timeout={(QUERY_TIMEOUT_SECS*1000)}")
            rs = conn.execute(text(final_sql), params)
            rows = [list(r) for r in rs.fetchall()]
            cols = list(rs.keys())
            return {
                "sql": final_sql,
                "rowcount": len(rows),
                "columns": cols,
                "rows": rows,
            }
    except SQLAlchemyError as e:
        # Surface concise DB error to the client
        raise RuntimeError(f"Database error: {e}")


# --- Entry point --------------------------------------------------------------

if __name__ == "__main__":
    # FastMCP uses stdio transport by default; this blocks and serves forever.
    mcp.run()
