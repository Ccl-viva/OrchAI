from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from typing import Any

from .config import DB_PATH

_DB_LOCK = threading.Lock()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _dumps(data: dict[str, Any] | list[Any] | None) -> str:
    return json.dumps(data or {}, ensure_ascii=False)


def _loads(data: str | None) -> dict[str, Any]:
    if not data:
        return {}
    return json.loads(data)


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _DB_LOCK:
        conn = get_conn()
        try:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS workflow (
                    id TEXT PRIMARY KEY,
                    goal TEXT NOT NULL,
                    status TEXT NOT NULL,
                    parsed_goal TEXT NOT NULL,
                    state TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS nodes (
                    id TEXT PRIMARY KEY,
                    workflow_id TEXT NOT NULL,
                    order_index INTEGER NOT NULL,
                    type TEXT NOT NULL,
                    parameters TEXT NOT NULL,
                    status TEXT NOT NULL,
                    FOREIGN KEY (workflow_id) REFERENCES workflow (id)
                );

                CREATE TABLE IF NOT EXISTS execution_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    workflow_id TEXT NOT NULL,
                    node_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    result TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )
            conn.commit()
        finally:
            conn.close()


def create_workflow(goal: str, parsed_goal: dict[str, Any], nodes: list[dict[str, Any]]) -> str:
    workflow_id = str(uuid.uuid4())
    now = _utc_now()
    initial_state = {
        "uploaded_file": None,
        "columns": [],
        "preview": None,
        "selected_field": parsed_goal.get("field"),
        "aggregate_result": None,
        "exported_file": None,
    }

    with _DB_LOCK:
        conn = get_conn()
        try:
            conn.execute(
                """
                INSERT INTO workflow (id, goal, status, parsed_goal, state, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (workflow_id, goal, "created", _dumps(parsed_goal), _dumps(initial_state), now),
            )

            for index, node in enumerate(nodes):
                conn.execute(
                    """
                    INSERT INTO nodes (id, workflow_id, order_index, type, parameters, status)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(uuid.uuid4()),
                        workflow_id,
                        index,
                        node["type"],
                        _dumps(node.get("parameters", {})),
                        "pending",
                    ),
                )

            conn.commit()
        finally:
            conn.close()

    return workflow_id


def _read_nodes(conn: sqlite3.Connection, workflow_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT id, workflow_id, order_index, type, parameters, status
        FROM nodes
        WHERE workflow_id = ?
        ORDER BY order_index ASC
        """,
        (workflow_id,),
    ).fetchall()
    return [
        {
            "id": row["id"],
            "workflow_id": row["workflow_id"],
            "order_index": row["order_index"],
            "type": row["type"],
            "parameters": _loads(row["parameters"]),
            "status": row["status"],
        }
        for row in rows
    ]


def get_workflow(workflow_id: str) -> dict[str, Any] | None:
    conn = get_conn()
    try:
        row = conn.execute(
            """
            SELECT id, goal, status, parsed_goal, state, created_at
            FROM workflow
            WHERE id = ?
            """,
            (workflow_id,),
        ).fetchone()
        if not row:
            return None
        return {
            "id": row["id"],
            "goal": row["goal"],
            "status": row["status"],
            "parsed_goal": _loads(row["parsed_goal"]),
            "state": _loads(row["state"]),
            "created_at": row["created_at"],
            "nodes": _read_nodes(conn, workflow_id),
        }
    finally:
        conn.close()


def update_workflow(
    workflow_id: str,
    *,
    status: str | None = None,
    state: dict[str, Any] | None = None,
) -> None:
    with _DB_LOCK:
        conn = get_conn()
        try:
            if status is not None and state is not None:
                conn.execute(
                    "UPDATE workflow SET status = ?, state = ? WHERE id = ?",
                    (status, _dumps(state), workflow_id),
                )
            elif status is not None:
                conn.execute("UPDATE workflow SET status = ? WHERE id = ?", (status, workflow_id))
            elif state is not None:
                conn.execute("UPDATE workflow SET state = ? WHERE id = ?", (_dumps(state), workflow_id))
            conn.commit()
        finally:
            conn.close()


def update_node(node_id: str, *, status: str) -> None:
    with _DB_LOCK:
        conn = get_conn()
        try:
            conn.execute("UPDATE nodes SET status = ? WHERE id = ?", (status, node_id))
            conn.commit()
        finally:
            conn.close()


def get_next_pending_node(workflow_id: str) -> dict[str, Any] | None:
    conn = get_conn()
    try:
        row = conn.execute(
            """
            SELECT id, workflow_id, order_index, type, parameters, status
            FROM nodes
            WHERE workflow_id = ? AND status = 'pending'
            ORDER BY order_index ASC
            LIMIT 1
            """,
            (workflow_id,),
        ).fetchone()
        if not row:
            return None
        return {
            "id": row["id"],
            "workflow_id": row["workflow_id"],
            "order_index": row["order_index"],
            "type": row["type"],
            "parameters": _loads(row["parameters"]),
            "status": row["status"],
        }
    finally:
        conn.close()


def get_node_by_type(workflow_id: str, node_type: str) -> dict[str, Any] | None:
    conn = get_conn()
    try:
        row = conn.execute(
            """
            SELECT id, workflow_id, order_index, type, parameters, status
            FROM nodes
            WHERE workflow_id = ? AND type = ?
            ORDER BY order_index ASC
            LIMIT 1
            """,
            (workflow_id, node_type),
        ).fetchone()
        if not row:
            return None
        return {
            "id": row["id"],
            "workflow_id": row["workflow_id"],
            "order_index": row["order_index"],
            "type": row["type"],
            "parameters": _loads(row["parameters"]),
            "status": row["status"],
        }
    finally:
        conn.close()


def log_execution(workflow_id: str, node_id: str, status: str, result: dict[str, Any]) -> None:
    with _DB_LOCK:
        conn = get_conn()
        try:
            conn.execute(
                """
                INSERT INTO execution_log (workflow_id, node_id, status, result, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (workflow_id, node_id, status, _dumps(result), _utc_now()),
            )
            conn.commit()
        finally:
            conn.close()
