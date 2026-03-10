export type NodeStatus = "pending" | "success" | "failed" | "running" | "waiting";

export interface WorkflowNode {
  id: string;
  order_index: number;
  type: string;
  status: NodeStatus | string;
  parameters: Record<string, unknown>;
}

export interface NodeConversationMessage {
  role: string;
  content: string;
}

export interface PreviewData {
  type: string;
  columns: string[];
  rows: Array<Array<string | number>>;
}

export interface WorkflowData {
  id: string;
  goal: string;
  status: string;
  source_type?: string;
  parsed_goal: Record<string, unknown>;
  state: Record<string, unknown>;
  adapter_state?: Record<string, unknown>;
  nodes: WorkflowNode[];
  created_at: string;
}

export interface ExecuteEvent {
  node_id: string;
  node_type: string;
  status: string;
  message: string;
  preview?: PreviewData;
  payload: Record<string, unknown>;
}

export interface PendingConfirmation {
  message: string;
  options: string[];
}

export interface ExecuteResponse {
  workflow: WorkflowData;
  events: ExecuteEvent[];
  pending_confirmation?: PendingConfirmation;
}

export interface NodeChatResponse {
  workflow: WorkflowData;
  node_id: string;
  reply: string;
  applied_updates: Record<string, unknown>;
}
