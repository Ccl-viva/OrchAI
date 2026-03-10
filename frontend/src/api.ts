import axios from "axios";
import type { ExecuteResponse, NodeChatResponse, WorkflowData } from "./types";

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE ?? "http://localhost:8000"
});

export async function createTask(goal: string): Promise<{ workflow_id: string; workflow: WorkflowData }> {
  const response = await api.post("/task/create", { goal });
  return response.data;
}

export async function uploadTaskFile(workflowId: string, file: File): Promise<{ workflow: WorkflowData }> {
  const formData = new FormData();
  formData.append("workflow_id", workflowId);
  formData.append("file", file);
  const response = await api.post("/task/upload", formData, {
    headers: { "Content-Type": "multipart/form-data" }
  });
  return response.data;
}

export async function executeWorkflow(workflowId: string, confirmValue?: string): Promise<ExecuteResponse> {
  const response = await api.post("/workflow/execute", {
    workflow_id: workflowId,
    confirm_value: confirmValue
  });
  return response.data;
}

export async function fetchWorkflow(workflowId: string): Promise<WorkflowData> {
  const response = await api.get(`/workflow/${workflowId}`);
  return response.data;
}

export async function chatNode(workflowId: string, nodeId: string, message: string): Promise<NodeChatResponse> {
  const response = await api.post("/node/chat", {
    workflow_id: workflowId,
    node_id: nodeId,
    message
  });
  return response.data;
}
