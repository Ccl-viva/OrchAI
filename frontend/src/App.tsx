import { type CSSProperties, useEffect, useMemo, useState } from "react";
import { Button, Input, Select, Space, Table, Tabs, Tag, Typography, Upload, message } from "antd";
import type { UploadProps } from "antd";
import ReactFlow, {
  Background,
  BackgroundVariant,
  Controls,
  Handle,
  Position,
  useNodesState,
  type Edge,
  type Node,
  type NodeProps
} from "reactflow";

import { chatNode, createTask, executeWorkflow, uploadTaskFile } from "./api";
import type {
  ExecuteEvent,
  NodeConversationMessage,
  PendingConfirmation,
  PreviewData,
  WorkflowData,
  WorkflowNode
} from "./types";

const { Title, Text } = Typography;

const NODE_LABELS: Record<string, string> = {
  upload_file: "Upload File",
  parse_excel: "Parse Excel",
  user_confirm: "User Confirm",
  aggregate: "Aggregate Sum",
  export_excel: "Export Result"
};

const STATUS_COLORS: Record<string, string> = {
  pending: "#8b98aa",
  success: "#299d6a",
  failed: "#d65050",
  running: "#2f7cf5",
  waiting: "#f3a638"
};

const NODE_DETAILS: Record<string, { description: string; purpose: string }> = {
  upload_file: {
    description: "Collect the source Excel file.",
    purpose: "Provide input data for downstream nodes."
  },
  parse_excel: {
    description: "Read and parse Excel into structured rows.",
    purpose: "Expose available fields and sample data."
  },
  user_confirm: {
    description: "Ask user to confirm ambiguous choices.",
    purpose: "Avoid wrong field mapping before aggregation."
  },
  aggregate: {
    description: "Compute summary metric on selected field.",
    purpose: "Produce the target numeric result."
  },
  export_excel: {
    description: "Export current result to an Excel file.",
    purpose: "Generate downloadable deliverable."
  }
};

type NodePosition = { x: number; y: number };

type FlowNodeData = {
  id: string;
  title: string;
  subtitle: string;
  description: string;
  purpose: string;
  conversation: NodeConversationMessage[];
  status: string;
  selected?: boolean;
  nodeType?: string;
  canExecute?: boolean;
  running?: boolean;
  canUpload?: boolean;
  onUpload?: (file: File) => Promise<void>;
  confirm?: PendingConfirmation | null;
  confirmValue?: string;
  onConfirmChange?: (value: string) => void;
  onConfirmSubmit?: () => void;
  confirmLoading?: boolean;
  onExecute?: () => void;
  onChatSend?: (nodeId: string, text: string) => Promise<void>;
  chatSending?: boolean;
};

function statusText(status: string): string {
  if (status === "pending") {
    return "Pending";
  }
  if (status === "success") {
    return "Done";
  }
  if (status === "failed") {
    return "Failed";
  }
  if (status === "running") {
    return "Running";
  }
  if (status === "waiting") {
    return "Waiting";
  }
  return status;
}

function shortGoal(goal: string): string {
  if (goal.length <= 26) {
    return goal;
  }
  return `${goal.slice(0, 26)}...`;
}

function findLatestPreview(events: ExecuteEvent[], workflow: WorkflowData | null): PreviewData | undefined {
  for (let i = events.length - 1; i >= 0; i -= 1) {
    if (events[i].preview) {
      return events[i].preview;
    }
  }
  const fallback = workflow?.state?.preview;
  if (fallback && typeof fallback === "object") {
    return fallback as PreviewData;
  }
  return undefined;
}

function readStringParam(parameters: Record<string, unknown>, key: string, fallback = ""): string {
  const value = parameters[key];
  if (typeof value === "string" && value.trim()) {
    return value.trim();
  }
  return fallback;
}

function readConversation(parameters: Record<string, unknown>): NodeConversationMessage[] {
  const raw = parameters.conversation;
  if (!Array.isArray(raw)) {
    return [];
  }
  const messages: NodeConversationMessage[] = [];
  for (const item of raw) {
    if (!item || typeof item !== "object") {
      continue;
    }
    const role = String((item as Record<string, unknown>).role ?? "").trim();
    const content = String((item as Record<string, unknown>).content ?? "").trim();
    if (!role || !content) {
      continue;
    }
    messages.push({ role, content });
  }
  return messages.slice(-8);
}

function GoalNode({ data }: NodeProps<FlowNodeData>) {
  return (
    <div className={`rf-goal-node ${data.selected ? "rf-goal-selected" : ""}`}>
      <div className="rf-goal-kicker">GOAL</div>
      <div className="rf-goal-title">{data.title}</div>
      <div className="rf-goal-sub">{data.subtitle}</div>
      <Handle type="source" position={Position.Right} className="rf-handle" />
    </div>
  );
}

function StepNode({ data }: NodeProps<FlowNodeData>) {
  const [chatText, setChatText] = useState("");

  const uploadProps: UploadProps = {
    maxCount: 1,
    showUploadList: false,
    customRequest: async (options) => {
      try {
        const file = options.file as File;
        await data.onUpload?.(file);
        options.onSuccess?.({}, options.file);
      } catch (error) {
        options.onError?.(new Error(String(error)));
      }
    }
  };

  async function submitChat() {
    if (!data.onChatSend) {
      return;
    }
    const text = chatText.trim();
    if (!text) {
      return;
    }
    await data.onChatSend(data.id, text);
    setChatText("");
  }

  return (
    <div
      className={`rf-step-node rf-step-${data.status} ${data.selected ? "rf-step-selected" : ""}`}
      style={
        {
          "--status-color": STATUS_COLORS[data.status] ?? STATUS_COLORS.pending
        } as CSSProperties
      }
    >
      <Handle type="target" position={Position.Left} className="rf-handle" />

      <div className="rf-step-header">
        <div className="rf-step-title">{data.title}</div>
      </div>

      <div className="rf-step-body">
        <div className="rf-step-sub">{data.subtitle}</div>
        <div className="rf-step-meta">
          <div className="rf-step-meta-title">Description</div>
          <div>{data.description}</div>
          <div className="rf-step-meta-title">Purpose</div>
          <div>{data.purpose}</div>
        </div>

        {data.canUpload && (
          <div className="nodrag nopan rf-step-action">
            <Upload {...uploadProps}>
              <Button size="small" block>
                Upload Excel
              </Button>
            </Upload>
          </div>
        )}

        {data.confirm && data.nodeType === "user_confirm" && (
          <div className="nodrag nopan rf-step-action-stack">
            <Select
              size="small"
              value={data.confirmValue}
              onChange={data.onConfirmChange}
              options={data.confirm.options.map((option) => ({ value: option, label: option }))}
            />
            <Button size="small" type="primary" onClick={data.onConfirmSubmit} loading={data.confirmLoading}>
              Confirm
            </Button>
          </div>
        )}

        {data.canExecute && (
          <div className="nodrag nopan rf-step-action">
            <Button size="small" type="primary" block loading={data.running} onClick={data.onExecute}>
              Run Step
            </Button>
          </div>
        )}

        <div className="nodrag nopan rf-step-chat">
          <div className="rf-step-chat-title">Node Chat</div>
          {data.conversation.length > 0 && (
            <div className="rf-step-chat-history">
              {data.conversation.map((item, index) => (
                <div
                  // eslint-disable-next-line react/no-array-index-key
                  key={`${data.id}-chat-${index}`}
                  className={`rf-step-chat-item ${item.role === "user" ? "rf-step-chat-user" : "rf-step-chat-assistant"}`}
                >
                  <strong>{item.role === "user" ? "You" : "System"}:</strong> {item.content}
                </div>
              ))}
            </div>
          )}
          <Input.TextArea
            value={chatText}
            onChange={(event) => setChatText(event.target.value)}
            autoSize={{ minRows: 1, maxRows: 3 }}
            placeholder="Ask to modify this node action..."
          />
          <Button size="small" onClick={submitChat} loading={data.chatSending}>
            Send
          </Button>
        </div>
      </div>

      <Handle type="source" position={Position.Right} className="rf-handle" />
    </div>
  );
}

const nodeTypes = {
  goal: GoalNode,
  step: StepNode
};

function defaultPosition(index: number): NodePosition {
  return {
    x: 460 + index * 295,
    y: 220 + (index % 2 === 0 ? -88 : 88)
  };
}

export default function App() {
  const [goal, setGoal] = useState("Sum price from an Excel file");
  const [workflow, setWorkflow] = useState<WorkflowData | null>(null);
  const [events, setEvents] = useState<ExecuteEvent[]>([]);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [pendingConfirm, setPendingConfirm] = useState<PendingConfirmation | null>(null);
  const [confirmValue, setConfirmValue] = useState<string>("");
  const [creatingTask, setCreatingTask] = useState(false);
  const [runningWorkflow, setRunningWorkflow] = useState(false);
  const [submittingConfirm, setSubmittingConfirm] = useState(false);
  const [chattingNodeId, setChattingNodeId] = useState<string | null>(null);
  const [flowNodes, setFlowNodes, onFlowNodesChange] = useNodesState<FlowNodeData>([]);

  const apiBase = import.meta.env.VITE_API_BASE ?? "http://localhost:8000";
  const preview = useMemo(() => findLatestPreview(events, workflow), [events, workflow]);

  const orderedNodes = useMemo<WorkflowNode[]>(() => {
    if (!workflow) {
      return [];
    }
    return workflow.nodes.slice().sort((a, b) => a.order_index - b.order_index);
  }, [workflow]);

  const nextPendingNode = useMemo(() => orderedNodes.find((node) => node.status === "pending") ?? null, [orderedNodes]);

  const selectedNode = useMemo(() => {
    if (!selectedNodeId) {
      return null;
    }
    return orderedNodes.find((item) => item.id === selectedNodeId) ?? null;
  }, [orderedNodes, selectedNodeId]);

  async function handleNodeUpload(file: File) {
    if (!workflow) {
      message.error("Create a task first.");
      return;
    }
    const result = await uploadTaskFile(workflow.id, file);
    setWorkflow(result.workflow);
    message.success("Upload complete.");
  }

  async function runWorkflow(confirm?: string) {
    if (!workflow) {
      message.error("Create a task first.");
      return;
    }

    setRunningWorkflow(true);
    try {
      const result = await executeWorkflow(workflow.id, confirm);
      setWorkflow(result.workflow);
      setEvents((prev) => [...prev, ...result.events]);
      setPendingConfirm(result.pending_confirmation ?? null);

      if (result.pending_confirmation) {
        setConfirmValue(result.pending_confirmation.options[0] ?? "");
        message.info("Paused at confirm step.");
      } else if (result.workflow.status === "completed") {
        message.success("Workflow completed.");
      }
    } catch (error) {
      message.error(`Run failed: ${String(error)}`);
    } finally {
      setRunningWorkflow(false);
    }
  }

  async function handleNodeChat(nodeId: string, text: string) {
    if (!workflow) {
      message.error("Create a task first.");
      return;
    }

    setChattingNodeId(nodeId);
    try {
      const result = await chatNode(workflow.id, nodeId, text);
      setWorkflow(result.workflow);
      if (Object.keys(result.applied_updates).length > 0) {
        message.success(result.reply);
      } else {
        message.info(result.reply);
      }
    } catch (error) {
      message.error(`Node chat failed: ${String(error)}`);
    } finally {
      setChattingNodeId(null);
    }
  }

  async function submitConfirmation() {
    if (!confirmValue) {
      message.error("Choose a field first.");
      return;
    }
    setSubmittingConfirm(true);
    try {
      await runWorkflow(confirmValue);
      setPendingConfirm(null);
    } finally {
      setSubmittingConfirm(false);
    }
  }

  async function handleCreateTask() {
    if (!goal.trim()) {
      message.error("Enter a goal first.");
      return;
    }

    setCreatingTask(true);
    try {
      const created = await createTask(goal.trim());
      setWorkflow(created.workflow);
      setEvents([]);
      setPendingConfirm(null);
      setConfirmValue("");
      setChattingNodeId(null);
      setSelectedNodeId(created.workflow.nodes[0]?.id ?? "goal");
      message.success("Moved into canvas.");
    } catch (error) {
      message.error(`Create failed: ${String(error)}`);
    } finally {
      setCreatingTask(false);
    }
  }

  function resetWorkspace() {
    setWorkflow(null);
    setEvents([]);
    setSelectedNodeId(null);
    setPendingConfirm(null);
    setConfirmValue("");
    setChattingNodeId(null);
    setFlowNodes([]);
  }

  useEffect(() => {
    if (!workflow) {
      setFlowNodes([]);
      return;
    }

    setFlowNodes((prev) => {
      const prevMap = new Map(prev.map((node) => [node.id, node]));
      const nodes: Node<FlowNodeData>[] = [
        {
          id: "goal",
          type: "goal",
          position: prevMap.get("goal")?.position ?? { x: 140, y: 220 },
          data: {
            id: "goal",
            title: shortGoal(workflow.goal),
            subtitle: "Drag to reposition",
            description: "Top-level objective provided by the user.",
            purpose: "Guide planner to build downstream workflow nodes.",
            conversation: [],
            status: "success",
            selected: selectedNodeId === "goal"
          },
          draggable: true
        }
      ];

      orderedNodes.forEach((node, index) => {
        const isCurrent = nextPendingNode?.id === node.id;
        const isUpload = node.type === "upload_file";
        const isConfirm = node.type === "user_confirm";
        const parameters = node.parameters as Record<string, unknown>;
        const defaults = NODE_DETAILS[node.type] ?? {
          description: "Execute this node task.",
          purpose: "Drive workflow to next state."
        };

        nodes.push({
          id: node.id,
          type: "step",
          position: prevMap.get(node.id)?.position ?? defaultPosition(index),
          data: {
            id: node.id,
            title: NODE_LABELS[node.type] ?? node.type,
            subtitle: statusText(node.status),
            description: readStringParam(parameters, "description", defaults.description),
            purpose: readStringParam(parameters, "purpose", defaults.purpose),
            conversation: readConversation(parameters),
            status: node.status,
            nodeType: node.type,
            selected: selectedNodeId === node.id,
            canUpload: isCurrent && isUpload && node.status === "pending",
            onUpload: handleNodeUpload,
            canExecute: isCurrent && !isUpload && !isConfirm && node.status === "pending" && !pendingConfirm,
            running: runningWorkflow,
            onExecute: () => runWorkflow(),
            confirm: isCurrent && isConfirm ? pendingConfirm : null,
            confirmValue,
            onConfirmChange: setConfirmValue,
            onConfirmSubmit: submitConfirmation,
            confirmLoading: submittingConfirm,
            onChatSend: handleNodeChat,
            chatSending: chattingNodeId === node.id
          },
          draggable: true
        });
      });

      return nodes;
    });
  }, [
    chattingNodeId,
    confirmValue,
    nextPendingNode,
    orderedNodes,
    pendingConfirm,
    runningWorkflow,
    selectedNodeId,
    setFlowNodes,
    submittingConfirm,
    workflow
  ]);

  const flowEdges = useMemo<Edge[]>(() => {
    if (!workflow || orderedNodes.length === 0) {
      return [];
    }

    const edges: Edge[] = [];
    const first = orderedNodes[0];
    edges.push({
      id: `goal-${first.id}`,
      source: "goal",
      target: first.id,
      type: "bezier",
      animated: false,
      style: {
        stroke: "#b9c3d0",
        strokeWidth: 2.4,
        strokeDasharray: "8 8",
        strokeLinecap: "round"
      }
    });

    for (let index = 0; index < orderedNodes.length - 1; index += 1) {
      const source = orderedNodes[index];
      const target = orderedNodes[index + 1];
      const color = source.status === "success" ? "#9ccbb0" : "#b9c3d0";
      edges.push({
        id: `${source.id}-${target.id}`,
        source: source.id,
        target: target.id,
        type: "bezier",
        animated: false,
        style: {
          stroke: color,
          strokeWidth: 2.4,
          strokeDasharray: "8 8",
          strokeLinecap: "round"
        }
      });
    }
    return edges;
  }, [workflow, orderedNodes]);

  const tableColumns = (preview?.columns ?? []).map((column) => ({
    title: column,
    dataIndex: column,
    key: column
  }));

  const tableData = (preview?.rows ?? []).map((row, index) => {
    const item: Record<string, string | number> = {};
    (preview?.columns ?? []).forEach((column, columnIndex) => {
      item[column] = row[columnIndex] ?? "";
    });
    return { key: `${index}`, ...item };
  });

  const sidebarItems = [
    {
      key: "preview",
      label: "Preview",
      children: preview ? (
        <Table pagination={false} columns={tableColumns} dataSource={tableData} size="small" scroll={{ x: true }} />
      ) : (
        <Text type="secondary">Preview appears after node execution.</Text>
      )
    },
    {
      key: "node",
      label: "Node",
      children: selectedNode ? (
        <Space direction="vertical" style={{ width: "100%" }}>
          <Space>
            <Text strong>{NODE_LABELS[selectedNode.type] ?? selectedNode.type}</Text>
            <Tag color={selectedNode.status === "success" ? "green" : selectedNode.status === "failed" ? "red" : "blue"}>
              {statusText(selectedNode.status)}
            </Tag>
          </Space>
          <pre className="json-view">{JSON.stringify(selectedNode.parameters, null, 2)}</pre>
        </Space>
      ) : (
        <Text type="secondary">Click a node in canvas for details.</Text>
      )
    },
    {
      key: "events",
      label: "Logs",
      children: (
        <div className="event-list">
          {events.length === 0 ? (
            <Text type="secondary">No logs yet.</Text>
          ) : (
            events.map((event, index) => (
              <div className="event-item" key={`${event.node_id}-${index}`}>
                <Tag color={event.status === "success" ? "green" : event.status === "failed" ? "red" : "orange"}>
                  {NODE_LABELS[event.node_type] ?? event.node_type}
                </Tag>
                <Text>{event.message}</Text>
              </div>
            ))
          )}
        </div>
      )
    }
  ];

  return (
    <div className="app-shell">
      <header className="header-bar">
        <div className="header-main">
          <div>
            <Title level={3} style={{ margin: 0 }}>
              Goal Workflow Canvas
            </Title>
            <Text type="secondary">Controls live under each bubble card. Drag nodes freely.</Text>
          </div>
          {workflow?.status === "completed" && (
            <Button type="link" href={`${apiBase}/task/download/${workflow.id}`} target="_blank">
              Download Result
            </Button>
          )}
          <Button onClick={resetWorkspace}>New Goal</Button>
        </div>
      </header>

      {!workflow ? (
        <section className="entry-view">
          <div className="entry-goal-bubble">
            <Text className="entry-kicker">Enter your goal</Text>
            <Input.TextArea
              value={goal}
              onChange={(event) => setGoal(event.target.value)}
              rows={4}
              placeholder="Example: Sum price from an Excel file"
            />
            <Button type="primary" size="large" loading={creatingTask} onClick={handleCreateTask}>
              Enter Canvas
            </Button>
          </div>
        </section>
      ) : (
        <section className="workspace">
          <main className="canvas-panel">
            <div className="canvas-status">
              <Tag color={workflow.status === "completed" ? "green" : "blue"}>{workflow.status}</Tag>
              <Text type="secondary">{workflow.id}</Text>
              <Text type="secondary">Tip: drag any bubble to adjust layout.</Text>
            </div>

            <div className="canvas-board">
              <ReactFlow
                nodes={flowNodes}
                edges={flowEdges}
                nodeTypes={nodeTypes}
                nodesDraggable
                onNodesChange={onFlowNodesChange}
                onNodeClick={(_, node) => setSelectedNodeId(node.id)}
                onNodeDragStart={(_, node) => setSelectedNodeId(node.id)}
                zoomOnDoubleClick={false}
              >
                <Background variant={BackgroundVariant.Dots} color="#d3dae4" gap={24} size={1.4} />
                <Controls />
              </ReactFlow>
            </div>
          </main>

          <aside className="right-sidebar">
            <Tabs size="small" items={sidebarItems} />
          </aside>
        </section>
      )}
    </div>
  );
}
