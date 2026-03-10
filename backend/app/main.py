from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from .config import EXPORT_DIR, UPLOAD_DIR
from .db import (
    create_workflow,
    get_node,
    get_next_pending_node,
    get_node_by_type,
    get_workflow,
    init_db,
    log_execution,
    reset_nodes_from,
    update_node,
    update_node_data,
    update_workflow,
)
from .execution import execute_aggregate, execute_export_excel, execute_parse_excel
from .goal_parser import parse_goal
from .node_dialogue import apply_node_dialogue
from .planner import build_initial_nodes
from .schemas import (
    ExecuteEvent,
    ExecuteRequest,
    ExecuteResponse,
    NodeChatRequest,
    NodeChatResponse,
    PendingConfirmation,
    TaskCreateRequest,
    TaskCreateResponse,
    UploadResponse,
    WorkflowView,
)

app = FastAPI(title="Goal-Driven AI Workflow System Demo", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup() -> None:
    init_db()


def _workflow_view(raw: dict[str, Any]) -> WorkflowView:
    return WorkflowView(**raw)


def _safe_filename(name: str) -> str:
    return "".join(char for char in name if char.isalnum() or char in {"-", "_", "."}) or "upload.xlsx"


def _pending_event(node: dict[str, Any], message: str) -> ExecuteEvent:
    return ExecuteEvent(
        node_id=node["id"],
        node_type=node["type"],
        status="waiting",
        message=message,
    )


def _reset_state_from_node(node_type: str, state: dict[str, Any]) -> dict[str, Any]:
    updated = dict(state)
    if node_type in {"parse_excel", "upload_file"}:
        updated["columns"] = []
        updated["preview"] = None
        updated["selected_field"] = None
        updated["aggregate_result"] = None
        updated["exported_file"] = None
        return updated
    if node_type == "user_confirm":
        updated["selected_field"] = None
        updated["aggregate_result"] = None
        updated["exported_file"] = None
        return updated
    if node_type == "aggregate":
        updated["aggregate_result"] = None
        updated["exported_file"] = None
        return updated
    if node_type == "export_excel":
        updated["exported_file"] = None
        return updated
    return updated


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/task/create", response_model=TaskCreateResponse)
def create_task(payload: TaskCreateRequest) -> TaskCreateResponse:
    parsed_goal = parse_goal(payload.goal)
    nodes = build_initial_nodes(parsed_goal)
    workflow_id = create_workflow(payload.goal, parsed_goal, nodes)
    workflow = get_workflow(workflow_id)
    if not workflow:
        raise HTTPException(status_code=500, detail="Failed to create workflow.")
    return TaskCreateResponse(workflow_id=workflow_id, workflow=_workflow_view(workflow))


@app.post("/task/upload", response_model=UploadResponse)
def upload_file(workflow_id: str = Form(...), file: UploadFile = File(...)) -> UploadResponse:
    workflow = get_workflow(workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found.")

    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in {".xlsx", ".xls"}:
        raise HTTPException(status_code=400, detail="Only Excel files are supported.")

    file_name = f"{workflow_id}_{_safe_filename(file.filename or 'upload.xlsx')}"
    file_path = Path(UPLOAD_DIR) / file_name
    with file_path.open("wb") as output:
        shutil.copyfileobj(file.file, output)

    state = workflow["state"]
    state["uploaded_file"] = str(file_path)
    state["upload_file_name"] = file.filename
    update_workflow(workflow_id, state=state, status="ready")

    input_node = get_node_by_type(workflow_id, "upload_file")
    if input_node and input_node["status"] == "pending":
        update_node(input_node["id"], status="success")
        log_execution(
            workflow_id,
            input_node["id"],
            "success",
            {"message": "File uploaded successfully.", "file_name": file.filename},
        )

    updated = get_workflow(workflow_id)
    if not updated:
        raise HTTPException(status_code=500, detail="Workflow state unavailable after upload.")
    return UploadResponse(workflow_id=workflow_id, file_name=file.filename or file_name, workflow=_workflow_view(updated))


def _confirm_field_value(options: list[str], value: str) -> str:
    if value in options:
        return value
    lowered = {item.lower(): item for item in options}
    if value.lower() in lowered:
        return lowered[value.lower()]
    raise HTTPException(status_code=400, detail=f"Invalid field '{value}', options: {options}")


@app.post("/node/chat", response_model=NodeChatResponse)
def node_chat(payload: NodeChatRequest) -> NodeChatResponse:
    message_text = payload.message.strip()
    if not message_text:
        raise HTTPException(status_code=400, detail="Message cannot be empty.")

    workflow = get_workflow(payload.workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found.")

    node = get_node(payload.node_id)
    if not node or node["workflow_id"] != payload.workflow_id:
        raise HTTPException(status_code=404, detail="Node not found in this workflow.")

    parameters, reply, applied_updates, state_patch, should_reset = apply_node_dialogue(
        node=node,
        workflow=workflow,
        message=message_text,
    )

    update_node_data(node["id"], parameters=parameters)

    state = dict(workflow["state"])
    if state_patch:
        state.update(state_patch)

    if should_reset and node["status"] == "success":
        state = _reset_state_from_node(node["type"], state)
        reset_nodes_from(payload.workflow_id, node["order_index"])
        update_workflow(payload.workflow_id, state=state, status="ready")
    elif state_patch:
        update_workflow(payload.workflow_id, state=state)

    log_execution(
        payload.workflow_id,
        node["id"],
        "info",
        {"message": "Node dialogue update", "user_message": message_text, "reply": reply, "updates": applied_updates},
    )

    updated_workflow = get_workflow(payload.workflow_id)
    if not updated_workflow:
        raise HTTPException(status_code=500, detail="Workflow unavailable after node update.")

    return NodeChatResponse(
        workflow=_workflow_view(updated_workflow),
        node_id=node["id"],
        reply=reply,
        applied_updates=applied_updates,
    )


@app.post("/workflow/execute", response_model=ExecuteResponse)
def execute_workflow(payload: ExecuteRequest) -> ExecuteResponse:
    workflow_id = payload.workflow_id
    confirm_value = payload.confirm_value
    workflow = get_workflow(workflow_id)

    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found.")

    events: list[ExecuteEvent] = []
    update_workflow(workflow_id, status="running")

    while True:
        workflow = get_workflow(workflow_id)
        if not workflow:
            raise HTTPException(status_code=500, detail="Workflow lost during execution.")

        node = get_next_pending_node(workflow_id)
        if not node:
            update_workflow(workflow_id, status="completed")
            completed = get_workflow(workflow_id)
            if not completed:
                raise HTTPException(status_code=500, detail="Workflow completed but unavailable.")
            return ExecuteResponse(workflow=_workflow_view(completed), events=events)

        state = workflow["state"]
        node_type = node["type"]

        if node_type == "upload_file":
            if not state.get("uploaded_file"):
                update_workflow(workflow_id, status="waiting_input")
                refreshed = get_workflow(workflow_id)
                if not refreshed:
                    raise HTTPException(status_code=500, detail="Workflow unavailable.")
                events.append(_pending_event(node, "Please upload an Excel file before execution."))
                return ExecuteResponse(workflow=_workflow_view(refreshed), events=events)
            update_node(node["id"], status="success")
            log_execution(workflow_id, node["id"], "success", {"message": "Upload node auto-completed."})
            events.append(
                ExecuteEvent(
                    node_id=node["id"],
                    node_type=node_type,
                    status="success",
                    message="Upload node completed.",
                )
            )
            continue

        if node_type == "parse_excel":
            try:
                state, result = execute_parse_excel(state, node.get("parameters", {}))
            except Exception as exc:
                update_node(node["id"], status="failed")
                update_workflow(workflow_id, status="failed")
                log_execution(workflow_id, node["id"], "failed", {"error": str(exc)})
                raise HTTPException(status_code=400, detail=f"Parse failed: {exc}") from exc

            update_workflow(workflow_id, state=state, status="running")
            update_node(node["id"], status="success")
            log_execution(workflow_id, node["id"], "success", result)
            events.append(
                ExecuteEvent(
                    node_id=node["id"],
                    node_type=node_type,
                    status="success",
                    message=result["message"],
                    preview=result.get("preview"),
                )
            )
            continue

        if node_type == "user_confirm":
            options_override = node["parameters"].get("options_override")
            if isinstance(options_override, list) and options_override:
                options = [str(item) for item in options_override]
            else:
                options = state.get("columns", [])
            current_selected = state.get("selected_field")
            message = node["parameters"].get("message", "Please select a field to continue.")

            if confirm_value:
                selected = _confirm_field_value(options, confirm_value)
                state["selected_field"] = selected
                confirm_value = None
                update_workflow(workflow_id, state=state, status="running")
                update_node(node["id"], status="success")
                result = {
                    "message": f"User confirmed field: {selected}.",
                    "payload": {"selected_field": selected},
                }
                log_execution(workflow_id, node["id"], "success", result)
                events.append(
                    ExecuteEvent(
                        node_id=node["id"],
                        node_type=node_type,
                        status="success",
                        message=result["message"],
                        payload=result["payload"],
                    )
                )
                continue

            if current_selected and current_selected in options:
                update_node(node["id"], status="success")
                result = {"message": f"Field already selected: {current_selected}."}
                log_execution(workflow_id, node["id"], "success", result)
                events.append(
                    ExecuteEvent(
                        node_id=node["id"],
                        node_type=node_type,
                        status="success",
                        message=result["message"],
                        payload={"selected_field": current_selected},
                    )
                )
                continue

            update_workflow(workflow_id, status="waiting_confirmation")
            log_execution(
                workflow_id,
                node["id"],
                "waiting",
                {"message": message, "options": options},
            )
            refreshed = get_workflow(workflow_id)
            if not refreshed:
                raise HTTPException(status_code=500, detail="Workflow unavailable.")
            return ExecuteResponse(
                workflow=_workflow_view(refreshed),
                events=events,
                pending_confirmation=PendingConfirmation(message=message, options=options),
            )

        if node_type == "aggregate":
            try:
                state, result = execute_aggregate(state, node["parameters"])
            except Exception as exc:
                update_node(node["id"], status="failed")
                update_workflow(workflow_id, status="failed")
                log_execution(workflow_id, node["id"], "failed", {"error": str(exc)})
                raise HTTPException(status_code=400, detail=f"Aggregate failed: {exc}") from exc

            update_workflow(workflow_id, state=state, status="running")
            update_node(node["id"], status="success")
            log_execution(workflow_id, node["id"], "success", result)
            events.append(
                ExecuteEvent(
                    node_id=node["id"],
                    node_type=node_type,
                    status="success",
                    message=result["message"],
                    preview=result.get("preview"),
                    payload=result.get("result", {}),
                )
            )
            continue

        if node_type == "export_excel":
            try:
                state, result = execute_export_excel(workflow_id, state, node.get("parameters", {}))
            except Exception as exc:
                update_node(node["id"], status="failed")
                update_workflow(workflow_id, status="failed")
                log_execution(workflow_id, node["id"], "failed", {"error": str(exc)})
                raise HTTPException(status_code=400, detail=f"Export failed: {exc}") from exc

            update_workflow(workflow_id, state=state, status="running")
            update_node(node["id"], status="success")
            log_execution(workflow_id, node["id"], "success", result)
            events.append(
                ExecuteEvent(
                    node_id=node["id"],
                    node_type=node_type,
                    status="success",
                    message=result["message"],
                    payload=result.get("payload", {}),
                )
            )
            continue

        raise HTTPException(status_code=400, detail=f"Unsupported node type: {node_type}")


@app.get("/workflow/{workflow_id}", response_model=WorkflowView)
def get_workflow_detail(workflow_id: str) -> WorkflowView:
    workflow = get_workflow(workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found.")
    return _workflow_view(workflow)


@app.get("/task/download/{workflow_id}")
def download_result(workflow_id: str) -> FileResponse:
    workflow = get_workflow(workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found.")

    exported_file = workflow["state"].get("exported_file")
    if not exported_file:
        raise HTTPException(status_code=404, detail="No exported file for this workflow.")

    file_path = Path(exported_file).resolve()
    export_root = Path(EXPORT_DIR).resolve()
    try:
        file_path.relative_to(export_root)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Export file not available.") from exc

    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Export file not available.")

    return FileResponse(path=file_path, filename=file_path.name)
