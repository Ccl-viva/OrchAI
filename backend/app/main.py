from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from .adapters.base import AdapterInputError, WorkflowAdapter
from .adapters.registry import get_adapter, resolve_source_type
from .config import EXPORT_DIR, UPLOAD_DIR
from .db import (
    add_node,
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
from .goal_parser import parse_goal
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


def _reset_state_from_node(node_type: str, state: dict[str, Any]) -> dict[str, Any]:
    updated = dict(state)
    if node_type in {"parse_excel", "parse_csv", "upload_file"}:
        updated["columns"] = []
        updated["preview"] = None
        updated["aggregate_result"] = None
        updated["exported_file"] = None
        return updated
    if node_type == "user_confirm":
        updated["aggregate_result"] = None
        updated["exported_file"] = None
        return updated
    if node_type == "aggregate":
        updated["aggregate_result"] = None
        updated["exported_file"] = None
        return updated
    if node_type in {"export_excel", "export_csv"}:
        updated["exported_file"] = None
        return updated
    return updated


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/task/create", response_model=TaskCreateResponse)
def create_task(payload: TaskCreateRequest) -> TaskCreateResponse:
    parsed_goal = parse_goal(payload.goal)
    source_type = resolve_source_type(parsed_goal)
    adapter = get_adapter(source_type)
    nodes = adapter.build_initial_nodes(parsed_goal)
    workflow_id = create_workflow(
        payload.goal,
        parsed_goal,
        nodes,
        source_type=source_type,
        adapter_state=adapter.default_adapter_state(parsed_goal),
    )
    workflow = get_workflow(workflow_id)
    if not workflow:
        raise HTTPException(status_code=500, detail="Failed to create workflow.")
    return TaskCreateResponse(workflow_id=workflow_id, workflow=_workflow_view(workflow))


@app.post("/task/upload", response_model=UploadResponse)
def upload_file(workflow_id: str = Form(...), file: UploadFile = File(...)) -> UploadResponse:
    workflow = get_workflow(workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found.")
    adapter = get_adapter(workflow.get("source_type"))

    suffix = Path(file.filename or "").suffix.lower()
    accepted_suffixes = adapter.accepted_file_suffixes
    if accepted_suffixes and suffix not in accepted_suffixes:
        expected = ", ".join(sorted(accepted_suffixes))
        raise HTTPException(status_code=400, detail=f"Unsupported file type '{suffix}', expected: {expected}")

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

    updated = _refresh_with_next_node(workflow_id, adapter=adapter, default_status="ready")
    return UploadResponse(workflow_id=workflow_id, file_name=file.filename or file_name, workflow=_workflow_view(updated))


def _ensure_next_node(workflow: dict[str, Any], *, adapter: WorkflowAdapter) -> dict[str, Any] | None:
    node = get_next_pending_node(workflow["id"])
    if node:
        return node

    planned = adapter.plan_next_node(
        workflow["parsed_goal"],
        workflow["state"],
        workflow.get("adapter_state", {}),
    )
    if not planned:
        return None

    node_id = add_node(workflow["id"], planned["type"], planned.get("parameters", {}), status="pending")
    return get_node(node_id)


def _refresh_with_next_node(
    workflow_id: str,
    *,
    adapter: WorkflowAdapter,
    default_status: str = "ready",
) -> dict[str, Any]:
    workflow = get_workflow(workflow_id)
    if not workflow:
        raise HTTPException(status_code=500, detail="Workflow unavailable.")

    next_node = _ensure_next_node(workflow, adapter=adapter)
    if next_node is None:
        update_workflow(workflow_id, status="completed")
    else:
        update_workflow(workflow_id, status=default_status)

    updated = get_workflow(workflow_id)
    if not updated:
        raise HTTPException(status_code=500, detail="Workflow unavailable.")
    return updated


@app.post("/node/chat", response_model=NodeChatResponse)
def node_chat(payload: NodeChatRequest) -> NodeChatResponse:
    message_text = payload.message.strip()
    if not message_text:
        raise HTTPException(status_code=400, detail="Message cannot be empty.")

    workflow = get_workflow(payload.workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found.")
    adapter = get_adapter(workflow.get("source_type"))

    node = get_node(payload.node_id)
    if not node or node["workflow_id"] != payload.workflow_id:
        raise HTTPException(status_code=404, detail="Node not found in this workflow.")

    parameters, reply, applied_updates, state_patch, should_reset = adapter.apply_node_dialogue(
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
    workflow = get_workflow(workflow_id)

    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found.")
    adapter = get_adapter(workflow.get("source_type"))

    events: list[ExecuteEvent] = []
    update_workflow(workflow_id, status="running")

    workflow = get_workflow(workflow_id)
    if not workflow:
        raise HTTPException(status_code=500, detail="Workflow lost during execution.")

    node = _ensure_next_node(workflow, adapter=adapter)
    if not node:
        update_workflow(workflow_id, status="completed")
        completed = get_workflow(workflow_id)
        if not completed:
            raise HTTPException(status_code=500, detail="Workflow completed but unavailable.")
        return ExecuteResponse(workflow=_workflow_view(completed), events=events)

    try:
        result = adapter.execute_node(
            workflow_id=workflow_id,
            node=node,
            state=workflow["state"],
            confirm_value=payload.confirm_value,
        )
    except AdapterInputError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        update_node(node["id"], status="failed")
        update_workflow(workflow_id, status="failed")
        log_execution(workflow_id, node["id"], "failed", {"error": str(exc)})
        raise HTTPException(status_code=400, detail=f"{node['type']} failed: {exc}") from exc

    if result.node_status:
        update_node(node["id"], status=result.node_status)

    update_workflow(workflow_id, state=result.state, status=result.workflow_status)

    if result.log_status:
        payload_data = result.log_result or {"message": result.event.get("message", "") if result.event else ""}
        log_execution(workflow_id, node["id"], result.log_status, payload_data)

    if result.event:
        events.append(ExecuteEvent(**result.event))

    if result.pending_confirmation is not None:
        pending = result.pending_confirmation
        pending_message = str(pending.get("message", "Please confirm to continue."))
        pending_options = [str(item) for item in pending.get("options", [])]
        refreshed = get_workflow(workflow_id)
        if not refreshed:
            raise HTTPException(status_code=500, detail="Workflow unavailable.")
        return ExecuteResponse(
            workflow=_workflow_view(refreshed),
            events=events,
            pending_confirmation=PendingConfirmation(message=pending_message, options=pending_options),
        )

    if result.advance:
        next_status = result.workflow_status if result.workflow_status not in {"running"} else "ready"
        updated = _refresh_with_next_node(workflow_id, adapter=adapter, default_status=next_status)
    else:
        updated = get_workflow(workflow_id)
        if not updated:
            raise HTTPException(status_code=500, detail="Workflow unavailable.")

    return ExecuteResponse(workflow=_workflow_view(updated), events=events)


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
