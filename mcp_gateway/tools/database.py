"""
Database Tool Provider - MCP tools for database operations.

Provides SQL query execution, table listing, and schema inspection.
Uses SQLite as the default backend for simplicity.
"""

from __future__ import annotations
import json
import sqlite3
import os
from typing import Any, Dict, List, Optional

from core.types import ToolDefinition, ToolCallResult
from core.exceptions import ToolExecutionError
from mcp_gateway.protocol import BaseToolProvider


class DatabaseToolProvider(BaseToolProvider):
    """Database tool provider using SQLite."""

    def __init__(self, db_path: str = "./data/mcp_gateway.db"):
        super().__init__(
            name="database",
            description="Database operations: SQL queries, table listing, schema inspection"
        )
        self._db_path = db_path
        self._register_tools()

    def _register_tools(self):
        self._register_tool(ToolDefinition(
            name="query",
            description="Execute a SELECT SQL query. Returns results as JSON array.",
            inputSchema={
                "type": "object",
                "properties": {
                    "sql": {
                        "type": "string",
                        "description": "SQL SELECT query to execute"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of rows to return (default: 100)",
                        "default": 100,
                    },
                },
                "required": ["sql"],
            },
            category="database",
            tags=["query", "select", "read"],
            cacheable=True,
            timeout_ms=15000,
        ))

        self._register_tool(ToolDefinition(
            name="execute",
            description="Execute a non-SELECT SQL statement (INSERT, UPDATE, DELETE, CREATE, etc.).",
            inputSchema={
                "type": "object",
                "properties": {
                    "sql": {
                        "type": "string",
                        "description": "SQL statement to execute"
                    },
                },
                "required": ["sql"],
            },
            category="database",
            tags=["execute", "write", "ddl"],
            cacheable=False,
            timeout_ms=15000,
        ))

        self._register_tool(ToolDefinition(
            name="list_tables",
            description="List all tables in the database.",
            inputSchema={
                "type": "object",
                "properties": {},
            },
            category="database",
            tags=["list", "tables", "schema"],
            cacheable=True,
            timeout_ms=5000,
        ))

        self._register_tool(ToolDefinition(
            name="describe_table",
            description="Describe the schema of a specific table (columns, types, constraints).",
            inputSchema={
                "type": "object",
                "properties": {
                    "table": {
                        "type": "string",
                        "description": "Table name to describe"
                    },
                },
                "required": ["table"],
            },
            category="database",
            tags=["describe", "schema", "table"],
            cacheable=True,
            timeout_ms=5000,
        ))

    def _get_connection(self) -> sqlite3.Connection:
        """Get a database connection."""
        os.makedirs(os.path.dirname(self._db_path) if os.path.dirname(self._db_path) else ".", exist_ok=True)
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        if tool_name == "query":
            return await self._query(**arguments)
        elif tool_name == "execute":
            return await self._execute(**arguments)
        elif tool_name == "list_tables":
            return await self._list_tables()
        elif tool_name == "describe_table":
            return await self._describe_table(**arguments)
        else:
            raise ToolExecutionError(tool_name, f"Unknown tool: {tool_name}")

    async def _query(self, sql: str, limit: int = 100) -> ToolCallResult:
        """Execute a SELECT query."""
        sql_upper = sql.strip().upper()
        if not sql_upper.startswith("SELECT") and not sql_upper.startswith("PRAGMA"):
            raise ToolExecutionError(
                "query",
                "Only SELECT queries are allowed. Use 'execute' for INSERT/UPDATE/DELETE."
            )

        # Add LIMIT if not present
        if "LIMIT" not in sql_upper:
            sql = f"{sql.rstrip(';')} LIMIT {limit}"

        try:
            conn = self._get_connection()
            cursor = conn.execute(sql)
            columns = [desc[0] for desc in cursor.description] if cursor.description else []
            rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
            conn.close()

            return ToolCallResult(
                tool_name="query",
                content=[{
                    "type": "text",
                    "text": json.dumps({
                        "columns": columns,
                        "row_count": len(rows),
                        "rows": rows,
                    }, ensure_ascii=False, indent=2, default=str),
                }],
            )
        except sqlite3.Error as e:
            raise ToolExecutionError("query", str(e))

    async def _execute(self, sql: str) -> ToolCallResult:
        """Execute a non-SELECT SQL statement."""
        sql_upper = sql.strip().upper()
        if sql_upper.startswith("SELECT"):
            raise ToolExecutionError(
                "execute",
                "SELECT queries should use 'query' tool instead."
            )

        try:
            conn = self._get_connection()
            cursor = conn.execute(sql)
            conn.commit()
            rowcount = cursor.rowcount
            conn.close()

            return ToolCallResult.text_result(
                "execute",
                f"Query executed successfully. Rows affected: {rowcount}"
            )
        except sqlite3.Error as e:
            raise ToolExecutionError("execute", str(e))

    async def _list_tables(self) -> ToolCallResult:
        """List all tables."""
        try:
            conn = self._get_connection()
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            )
            tables = [row[0] for row in cursor.fetchall()]
            conn.close()

            return ToolCallResult(
                tool_name="list_tables",
                content=[{
                    "type": "text",
                    "text": json.dumps({
                        "tables": tables,
                        "count": len(tables),
                    }, ensure_ascii=False, indent=2),
                }],
            )
        except sqlite3.Error as e:
            raise ToolExecutionError("list_tables", str(e))

    async def _describe_table(self, table: str) -> ToolCallResult:
        """Describe a table schema."""
        try:
            conn = self._get_connection()
            cursor = conn.execute(f"PRAGMA table_info({table})")
            columns = [
                {
                    "cid": row[0],
                    "name": row[1],
                    "type": row[2],
                    "notnull": bool(row[3]),
                    "default": row[4],
                    "pk": bool(row[5]),
                }
                for row in cursor.fetchall()
            ]
            conn.close()

            if not columns:
                raise ToolExecutionError("describe_table", f"Table '{table}' not found")

            return ToolCallResult(
                tool_name="describe_table",
                content=[{
                    "type": "text",
                    "text": json.dumps({
                        "table": table,
                        "columns": columns,
                    }, ensure_ascii=False, indent=2),
                }],
            )
        except sqlite3.Error as e:
            raise ToolExecutionError("describe_table", str(e))