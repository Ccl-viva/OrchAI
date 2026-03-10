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
                    source_type TEXT NOT NULL DEFAULT 'excel',
                    parsed_goal TEXT NOT NULL,
                    state TEXT NOT NULL,
                    adapter_state TEXT NOT NULL DEFAULT '{}',
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
            columns = {row["name"] for row in conn.execute("PRAGMA table_info(workflow)").fetchall()}
            if "source_type" not in columns:
                conn.execute("ALTER TABLE workflow ADD COLUMN source_type TEXT NOT NULL DEFAULT 'excel'")
            if "adapter_state" not in columns:
                conn.execute("ALTER TABLE workflow ADD COLUMN adapter_state TEXT NOT NULL DEFAULT '{}'")
            conn.commit()
        finally:
            conn.close()


def create_workflow(
    goal: str,
    parsed_goal: dict[str, Any],
    nodes: list[dict[str, Any]],
    *,
    source_type: str = "excel",
    adapter_state: dict[str, Any] | None = None,
) -> str:
    workflow_id = str(uuid.uuid4())
    now = _utc_now()
    method_value = parsed_goal.get("method")
    if isinstance(method_value, str):
        method_value = method_value.strip().lower() or None
    else:
        method_value = None
    if method_value in {"none", "null"}:
        method_value = None
    if method_value in {"avg", "average"}:
        method_value = "mean"

    initial_state = {
        "uploaded_file": None,
        "columns": [],
        "preview": None,
        "selected_field": parsed_goal.get("field"),
        "selected_method": method_value,
        "parse_sheet": None,
        "export_name": None,
        "aggregate_result": None,
        "exported_file": None,
    }

    with _DB_LOCK:
        conn = get_conn()
        try:
            conn.execute(
                """
                INSERT INTO workflow (id, goal, status, source_type, parsed_goal, state, adapter_state, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    workflow_id,
                    goal,
                    "created",
                    source_type,
                    _dumps(parsed_goal),
                    _dumps(initial_state),
                    _dumps(adapter_state or {}),
                    now,
                ),
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


def add_node(workflow_id: str, node_type: str, parameters: dict[str, Any] | None = None, status: str = "pending") -> str:
    node_id = str(uuid.uuid4())
    with _DB_LOCK:
        conn = get_conn()
        try:
            row = conn.execute(
                "SELECT COALESCE(MAX(order_index), -1) AS max_order FROM nodes WHERE workflow_id = ?",
                (workflow_id,),
            ).fetchone()
            max_order = int(row["max_order"]) if row and row["max_order"] is not None else -1
            next_order = max_order + 1

            conn.execute(
                """
                INSERT INTO nodes (id, workflow_id, order_index, type, parameters, status)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (node_id, workflow_id, next_order, node_type, _dumps(parameters or {}), status),
            )
            conn.commit()
        finally:
            conn.close()
    return node_id


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
            SELECT id, goal, status, source_type, parsed_goal, state, adapter_state, created_at
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
            "source_type": row["source_type"],
            "parsed_goal": _loads(row["parsed_goal"]),
            "state": _loads(row["state"]),
            "adapter_state": _loads(row["adapter_state"]),
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
    adapter_state: dict[str, Any] | None = None,
) -> None:
    if status is None and state is None and adapter_state is None:
        return

    with _DB_LOCK:
        conn = get_conn()
        try:
            assignments: list[str] = []
            values: list[Any] = []

            if status is not None:
                assignments.append("status = ?")
                values.append(status)
            if state is not None:
                assignments.append("state = ?")
                values.append(_dumps(state))
            if adapter_state is not None:
                assignments.append("adapter_state = ?")
                values.append(_dumps(adapter_state))

            values.append(workflow_id)
            query = f"UPDATE workflow SET {', '.join(assignments)} WHERE id = ?"
            conn.execute(query, tuple(values))
            conn.commit()
        finally:
            conn.close()


def update_node(node_id: str, *, status: str) -> None:
    update_node_data(node_id, status=status)


def update_node_data(
    node_id: str,
    *,
    status: str | None = None,
    parameters: dict[str, Any] | None = None,
) -> None:
    if status is None and parameters is None:
        return

    with _DB_LOCK:
        conn = get_conn()
        try:
            if status is not None and parameters is not None:
                conn.execute(
                    "UPDATE nodes SET status = ?, parameters = ? WHERE id = ?",
                    (status, _dumps(parameters), node_id),
                )
            elif status is not None:
                conn.execute("UPDATE nodes SET status = ? WHERE id = ?", (status, node_id))
            elif parameters is not None:
                conn.execute("UPDATE nodes SET parameters = ? WHERE id = ?", (_dumps(parameters), node_id))
            conn.commit()
        finally:
            conn.close()


def get_node(node_id: str) -> dict[str, Any] | None:
    conn = get_conn()
    try:
        row = conn.execute(
            """
            SELECT id, workflow_id, order_index, type, parameters, status
            FROM nodes
            WHERE id = ?
            LIMIT 1
            """,
            (node_id,),
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


def reset_nodes_from(workflow_id: str, start_order_index: int) -> None:
    with _DB_LOCK:
        conn = get_conn()
        try:
            conn.execute(
                """
                UPDATE nodes
                SET status = 'pending'
                WHERE workflow_id = ? AND order_index >= ?
                """,
                (workflow_id, start_order_index),
            )
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
