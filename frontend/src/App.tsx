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
  parse_csv: "Parse CSV",
  user_confirm: "Clarify",
  aggregate: "Aggregate Sum",
  export_excel: "Export Result",
  export_csv: "Export CSV"
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
  parse_csv: {
    description: "Read and parse CSV into structured rows.",
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
  },
  export_csv: {
    description: "Export current result to a CSV file.",
    purpose: "Generate downloadable deliverable."
  }
};

type NodePosition = { x: number; y: number };
type PreviewCellCoord = { row: number; col: number };
type PreviewSelection = { rowStart: number; rowEnd: number; colStart: number; colEnd: number };
type PreviewTableRow = { key: string } & Record<string, string | number>;
type PreviewMode = "table" | "chart" | "split";
type ColumnMetric = {
  count: number;
  sum: number;
  min: number;
  max: number;
  avg: number;
};
type ChartPoint = {
  rowIndex: number;
  label: string;
  value: number;
};

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
  responseText?: string;
  goalStatus?: string;
  goalHint?: string;
  downloadHref?: string;
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

function readStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return [];
  }
  const values: string[] = [];
  for (const item of value) {
    const text = String(item ?? "").trim();
    if (text) {
      values.push(text);
    }
  }
  return values;
}

function toNumber(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === "string") {
    const normalized = value.replace(/,/g, "").trim();
    if (!normalized) {
      return null;
    }
    const parsed = Number(normalized);
    if (Number.isFinite(parsed)) {
      return parsed;
    }
  }
  return null;
}

function formatMetric(value: number): string {
  if (!Number.isFinite(value)) {
    return "-";
  }
  if (Math.abs(value) >= 1000) {
    return value.toLocaleString(undefined, { maximumFractionDigits: 2 });
  }
  return value.toFixed(2).replace(/\.00$/, "");
}

function clampLabel(text: string, limit = 14): string {
  if (text.length <= limit) {
    return text;
  }
  return `${text.slice(0, limit)}...`;
}

function buildConfirmFromNode(node: WorkflowNode | null, workflow: WorkflowData | null): PendingConfirmation | null {
  if (!node || node.type !== "user_confirm" || node.status !== "pending") {
    return null;
  }

  const parameters = node.parameters as Record<string, unknown>;
  const messageText = readStringParam(parameters, "message", "Please select a field to continue.");
  const overrideOptions = readStringArray(parameters.options_override);
  const stateColumns = readStringArray(workflow?.state?.columns);
  const options = overrideOptions.length > 0 ? overrideOptions : stateColumns;

  return {
    message: messageText,
    options
  };
}

function buildUploadProps(onUpload?: (file: File) => Promise<void>): UploadProps {
  return {
    maxCount: 1,
    showUploadList: false,
    customRequest: async (options) => {
      try {
        const file = options.file as File;
        await onUpload?.(file);
        options.onSuccess?.({}, options.file);
      } catch (error) {
        options.onError?.(new Error(String(error)));
      }
    }
  };
}

function GoalNode({ data }: NodeProps<FlowNodeData>) {
  const uploadProps = buildUploadProps(data.onUpload);

  return (
    <div className={`rf-goal-node ${data.selected ? "rf-goal-selected" : ""}`}>
      <div className="rf-goal-kicker">GOAL</div>
      <div className="rf-goal-title">{data.title}</div>
      <div className="rf-goal-sub">{data.goalHint ?? data.subtitle}</div>
      <div className="rf-goal-state">{data.goalStatus ?? data.subtitle}</div>
      {data.canUpload && (
        <div className="nodrag nopan rf-goal-action">
          <Upload {...uploadProps}>
            <Button size="small" shape="round">
              Upload File
            </Button>
          </Upload>
        </div>
      )}
      {!data.canUpload && data.running && <div className="rf-goal-inline">AI is refining your request</div>}
      {!data.canUpload && data.downloadHref && (
        <Button size="small" shape="round" href={data.downloadHref} target="_blank">
          Download
        </Button>
      )}
      <Handle type="source" position={Position.Right} className="rf-handle" />
    </div>
  );
}

function StepNode({ data }: NodeProps<FlowNodeData>) {
  const [chatText, setChatText] = useState("");
  const uploadProps = buildUploadProps(data.onUpload);

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

        {data.responseText && <div className="rf-step-response">{data.responseText}</div>}

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
            <Text type="secondary">{data.confirm.message}</Text>
            <Select
              size="small"
              value={data.confirmValue || undefined}
              onChange={data.onConfirmChange}
              options={data.confirm.options.map((option) => ({ value: option, label: option }))}
              placeholder="Choose a field"
              disabled={data.confirm.options.length === 0}
            />
            <Button
              size="small"
              type="primary"
              onClick={data.onConfirmSubmit}
              loading={data.confirmLoading}
              disabled={!data.confirmValue}
            >
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
          <div className="rf-step-chat-title">Clarification Chat</div>
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
            placeholder="Clarify what you actually want here..."
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

const SIDEBAR_DEFAULT_WIDTH = 360;
const SIDEBAR_MIN_WIDTH = 280;
const SIDEBAR_MAX_WIDTH = 640;

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
  const [sidebarWidth, setSidebarWidth] = useState(SIDEBAR_DEFAULT_WIDTH);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [resizingSidebar, setResizingSidebar] = useState(false);
  const [previewDragActive, setPreviewDragActive] = useState(false);
  const [previewDragStart, setPreviewDragStart] = useState<PreviewCellCoord | null>(null);
  const [previewDragEnd, setPreviewDragEnd] = useState<PreviewCellCoord | null>(null);
  const [previewMode, setPreviewMode] = useState<PreviewMode>("split");

  const apiBase = import.meta.env.VITE_API_BASE ?? "http://localhost:8000";
  const preview = useMemo(() => findLatestPreview(events, workflow), [events, workflow]);

  const orderedNodes = useMemo<WorkflowNode[]>(() => {
    if (!workflow) {
      return [];
    }
    return workflow.nodes.slice().sort((a, b) => a.order_index - b.order_index);
  }, [workflow]);

  const nextPendingNode = useMemo(() => orderedNodes.find((node) => node.status === "pending") ?? null, [orderedNodes]);
  const visibleCanvasNodes = useMemo(
    () => orderedNodes.filter((node) => node.type === "user_confirm"),
    [orderedNodes]
  );
  const activeConfirm = useMemo(() => {
    if (!nextPendingNode || nextPendingNode.type !== "user_confirm") {
      return null;
    }
    return pendingConfirm ?? buildConfirmFromNode(nextPendingNode, workflow);
  }, [nextPendingNode, pendingConfirm, workflow]);
  const uploadNodePending = useMemo(
    () => Boolean(nextPendingNode && nextPendingNode.type === "upload_file" && nextPendingNode.status === "pending"),
    [nextPendingNode]
  );

  const selectedNode = useMemo(() => {
    if (!selectedNodeId || selectedNodeId === "goal") {
      return null;
    }
    return visibleCanvasNodes.find((item) => item.id === selectedNodeId) ?? null;
  }, [selectedNodeId, visibleCanvasNodes]);

  const canDragSelectInPreview = useMemo(() => {
    return Boolean(preview && preview.columns.length > 0 && preview.rows.length > 0);
  }, [preview]);

  const previewSelection = useMemo<PreviewSelection | null>(() => {
    if (!previewDragStart || !previewDragEnd) {
      return null;
    }
    return {
      rowStart: Math.min(previewDragStart.row, previewDragEnd.row),
      rowEnd: Math.max(previewDragStart.row, previewDragEnd.row),
      colStart: Math.min(previewDragStart.col, previewDragEnd.col),
      colEnd: Math.max(previewDragStart.col, previewDragEnd.col)
    };
  }, [previewDragEnd, previewDragStart]);

  const previewSelectedColumns = useMemo<string[]>(() => {
    if (!previewSelection || !preview) {
      return [];
    }
    return preview.columns.slice(previewSelection.colStart, previewSelection.colEnd + 1);
  }, [preview, previewSelection]);

  const previewResolvedConfirmValue = useMemo(() => {
    if (!activeConfirm || previewSelectedColumns.length !== 1) {
      return "";
    }
    const selectedColumn = previewSelectedColumns[0];
    const exact = activeConfirm.options.find((option) => option === selectedColumn);
    if (exact) {
      return exact;
    }
    const lower = activeConfirm.options.find((option) => option.toLowerCase() === selectedColumn.toLowerCase());
    return lower ?? "";
  }, [activeConfirm, previewSelectedColumns]);

  const previewSelectedRangeText = useMemo(() => {
    if (!previewSelection) {
      return "";
    }
    return `R${previewSelection.rowStart + 1}:R${previewSelection.rowEnd + 1} · C${previewSelection.colStart + 1}:C${previewSelection.colEnd + 1}`;
  }, [previewSelection]);

  const previewColumnMetrics = useMemo<Record<string, ColumnMetric>>(() => {
    const metrics: Record<string, ColumnMetric> = {};
    if (!preview || !preview.columns.length || !preview.rows.length) {
      return metrics;
    }

    for (let colIndex = 0; colIndex < preview.columns.length; colIndex += 1) {
      const column = preview.columns[colIndex];
      const numbers: number[] = [];
      for (const row of preview.rows) {
        const maybe = toNumber(row[colIndex]);
        if (maybe !== null) {
          numbers.push(maybe);
        }
      }
      if (!numbers.length) {
        continue;
      }
      const sum = numbers.reduce((acc, item) => acc + item, 0);
      metrics[column] = {
        count: numbers.length,
        sum,
        min: Math.min(...numbers),
        max: Math.max(...numbers),
        avg: sum / numbers.length
      };
    }

    return metrics;
  }, [preview]);

  const numericColumns = useMemo(() => Object.keys(previewColumnMetrics), [previewColumnMetrics]);

  const activeChartColumn = useMemo(() => {
    const selectedNumeric = previewSelectedColumns.find((column) => numericColumns.includes(column));
    if (selectedNumeric) {
      return selectedNumeric;
    }
    return numericColumns[0] ?? "";
  }, [numericColumns, previewSelectedColumns]);

  const chartPoints = useMemo<ChartPoint[]>(() => {
    if (!preview || !activeChartColumn) {
      return [];
    }

    const valueColumnIndex = preview.columns.findIndex((column) => column === activeChartColumn);
    if (valueColumnIndex < 0) {
      return [];
    }
    let labelColumnIndex = preview.columns.findIndex((column) => column !== activeChartColumn);
    if (labelColumnIndex < 0) {
      labelColumnIndex = valueColumnIndex;
    }

    const points: ChartPoint[] = [];
    for (let rowIndex = 0; rowIndex < preview.rows.length; rowIndex += 1) {
      const row = preview.rows[rowIndex];
      const value = toNumber(row[valueColumnIndex]);
      if (value === null) {
        continue;
      }
      const label = String(row[labelColumnIndex] ?? `Row ${rowIndex + 1}`).trim() || `Row ${rowIndex + 1}`;
      points.push({
        rowIndex,
        label: clampLabel(label),
        value
      });
      if (points.length >= 18) {
        break;
      }
    }
    return points;
  }, [activeChartColumn, preview]);

  const chartValueRange = useMemo(() => {
    if (!chartPoints.length) {
      return { min: 0, max: 0 };
    }
    const values = chartPoints.map((item) => item.value);
    return { min: Math.min(...values), max: Math.max(...values) };
  }, [chartPoints]);

  useEffect(() => {
    if (!activeConfirm) {
      return;
    }
    if (activeConfirm.options.length === 0) {
      setConfirmValue("");
      return;
    }
    if (!confirmValue || !activeConfirm.options.includes(confirmValue)) {
      setConfirmValue(activeConfirm.options[0]);
    }
  }, [activeConfirm, confirmValue]);

  useEffect(() => {
    if (!previewDragActive) {
      return;
    }
    const handleMouseUp = () => setPreviewDragActive(false);
    window.addEventListener("mouseup", handleMouseUp);
    return () => window.removeEventListener("mouseup", handleMouseUp);
  }, [previewDragActive]);

  useEffect(() => {
    if (!previewResolvedConfirmValue) {
      return;
    }
    if (confirmValue !== previewResolvedConfirmValue) {
      setConfirmValue(previewResolvedConfirmValue);
    }
  }, [confirmValue, previewResolvedConfirmValue]);

  useEffect(() => {
    setPreviewDragActive(false);
    setPreviewDragStart(null);
    setPreviewDragEnd(null);
  }, [activeConfirm, preview?.columns, preview?.rows]);

  async function handleNodeUpload(file: File) {
    if (!workflow) {
      message.error("Create a task first.");
      return;
    }
    const result = await uploadTaskFile(workflow.id, file);
    setWorkflow(result.workflow);
    setPendingConfirm(null);
    message.success("Upload complete.");
    await runWorkflow(undefined, result.workflow.id, "quiet");
  }

  async function runWorkflow(confirm?: string, workflowIdOverride?: string, toastMode: "default" | "quiet" = "default") {
    const workflowId = workflowIdOverride ?? workflow?.id;
    if (!workflowId) {
      message.error("Create a task first.");
      return;
    }

    setRunningWorkflow(true);
    try {
      const result = await executeWorkflow(workflowId, confirm);
      setWorkflow(result.workflow);
      setEvents((prev) => [...prev, ...result.events]);
      setPendingConfirm(result.pending_confirmation ?? null);

      if (result.pending_confirmation) {
        const pendingNode = result.workflow.nodes
          .slice()
          .sort((a, b) => a.order_index - b.order_index)
          .find((node) => node.status === "pending" && node.type === "user_confirm");
        setSelectedNodeId(pendingNode?.id ?? "goal");
        setConfirmValue(result.pending_confirmation.options[0] ?? "");
        if (toastMode === "default") {
          message.info("Need your input to continue.");
        }
      } else if (result.workflow.status === "completed") {
        setSelectedNodeId("goal");
        setConfirmValue("");
        if (toastMode === "default") {
          message.success("Workflow completed.");
        }
      }
      return result;
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
      setPendingConfirm(null);
      if (Object.keys(result.applied_updates).length > 0) {
        message.success(result.reply);
      } else {
        message.info(result.reply);
      }

      const refreshedPending = result.workflow.nodes
        .slice()
        .sort((a, b) => a.order_index - b.order_index)
        .find((item) => item.status === "pending");
      if (refreshedPending?.id === nodeId) {
        await runWorkflow(undefined, result.workflow.id, "quiet");
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
      setSelectedNodeId("goal");
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

  function startSidebarResize(event: React.MouseEvent<HTMLButtonElement>) {
    if (sidebarCollapsed) {
      return;
    }

    event.preventDefault();
    const startX = event.clientX;
    const startWidth = sidebarWidth;
    setResizingSidebar(true);

    const onMove = (moveEvent: MouseEvent) => {
      const delta = startX - moveEvent.clientX;
      const nextWidth = Math.min(SIDEBAR_MAX_WIDTH, Math.max(SIDEBAR_MIN_WIDTH, startWidth + delta));
      setSidebarWidth(nextWidth);
    };

    const onUp = () => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
      setResizingSidebar(false);
    };

    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
  }

  function beginPreviewDrag(event: React.MouseEvent<HTMLElement>, row: number, col: number) {
    if (!canDragSelectInPreview) {
      return;
    }
    event.preventDefault();
    setPreviewDragActive(true);
    setPreviewDragStart({ row, col });
    setPreviewDragEnd({ row, col });
  }

  function movePreviewDrag(row: number, col: number) {
    if (!previewDragActive) {
      return;
    }
    setPreviewDragEnd({ row, col });
  }

  function selectWholeColumn(col: number) {
    if (!preview || preview.rows.length === 0) {
      return;
    }
    setPreviewDragStart({ row: 0, col });
    setPreviewDragEnd({ row: preview.rows.length - 1, col });
    setPreviewDragActive(false);
  }

  function isPreviewCellSelected(row: number, col: number): boolean {
    if (!previewSelection) {
      return false;
    }
    return row >= previewSelection.rowStart && row <= previewSelection.rowEnd && col >= previewSelection.colStart && col <= previewSelection.colEnd;
  }

  useEffect(() => {
    if (!workflow) {
      setFlowNodes([]);
      return;
    }

    setFlowNodes((prev) => {
      const prevMap = new Map(prev.map((node) => [node.id, node]));
      const goalStatus =
        workflow.status === "completed"
          ? "Result ready"
          : uploadNodePending
            ? "Waiting for source file"
            : activeConfirm
              ? "Needs one clarification"
              : runningWorkflow || workflow.status === "running"
                ? "Refining your request"
                : workflow.status === "failed"
                  ? "Needs attention"
                  : "Following the inferred path";
      const goalHint =
        workflow.status === "completed"
          ? "The result is ready. Preview and download stay on the right."
          : uploadNodePending
            ? "Upload your spreadsheet. The system will hide technical steps and only ask when intent is unclear."
            : activeConfirm
              ? "Only the ambiguous decision is surfaced here."
              : "The system is handling internal steps in the background.";
      const nodes: Node<FlowNodeData>[] = [
        {
          id: "goal",
          type: "goal",
          position: prevMap.get("goal")?.position ?? { x: 140, y: 220 },
          data: {
            id: "goal",
            title: shortGoal(workflow.goal),
            subtitle: "Intent anchor",
            description: "Top-level objective provided by the user.",
            purpose: "Guide planner to fill in the hidden execution path.",
            conversation: [],
            status: "success",
            selected: selectedNodeId === "goal",
            goalStatus,
            goalHint,
            canUpload: uploadNodePending,
            onUpload: handleNodeUpload,
            running: runningWorkflow,
            downloadHref: workflow.status === "completed" ? `${apiBase}/task/download/${workflow.id}` : undefined
          },
          draggable: true
        }
      ];

      visibleCanvasNodes.forEach((node, index) => {
        const isCurrent = nextPendingNode?.id === node.id;
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
            subtitle: node.status === "pending" ? "Waiting for your choice" : statusText(node.status),
            description: readStringParam(parameters, "description", defaults.description),
            purpose: readStringParam(parameters, "purpose", defaults.purpose),
            conversation: readConversation(parameters),
            status: node.status,
            nodeType: node.type,
            responseText: readStringParam(parameters, "confirmed_value")
              ? `Chosen: ${readStringParam(parameters, "confirmed_value")}`
              : "",
            selected: selectedNodeId === node.id,
            canExecute: false,
            running: runningWorkflow,
            onExecute: () => runWorkflow(),
            confirm: isCurrent && isConfirm ? activeConfirm : null,
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
    activeConfirm,
    apiBase,
    nextPendingNode,
    pendingConfirm,
    runningWorkflow,
    selectedNodeId,
    setFlowNodes,
    submittingConfirm,
    uploadNodePending,
    visibleCanvasNodes,
    workflow
  ]);

  const flowEdges = useMemo<Edge[]>(() => {
    if (!workflow || visibleCanvasNodes.length === 0) {
      return [];
    }

    const edges: Edge[] = [];
    const first = visibleCanvasNodes[0];
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

    for (let index = 0; index < visibleCanvasNodes.length - 1; index += 1) {
      const source = visibleCanvasNodes[index];
      const target = visibleCanvasNodes[index + 1];
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
  }, [workflow, visibleCanvasNodes]);

  const tableColumns = (preview?.columns ?? []).map((column, columnIndex) => ({
    title: column,
    dataIndex: column,
    key: column,
    className:
      previewSelection && columnIndex >= previewSelection.colStart && columnIndex <= previewSelection.colEnd
        ? "preview-col-selected"
        : undefined,
    onCell: (_record: PreviewTableRow, rowIndex?: number) => {
      const safeRowIndex = typeof rowIndex === "number" ? rowIndex : -1;
      const selected = safeRowIndex >= 0 && isPreviewCellSelected(safeRowIndex, columnIndex);
      return {
        className: selected ? "preview-cell-selected" : canDragSelectInPreview ? "preview-cell-selectable" : undefined,
        onMouseDown: (event: React.MouseEvent<HTMLElement>) => {
          if (safeRowIndex >= 0) {
            beginPreviewDrag(event, safeRowIndex, columnIndex);
          }
        },
        onMouseEnter: () => {
          if (safeRowIndex >= 0) {
            movePreviewDrag(safeRowIndex, columnIndex);
          }
        },
        onMouseUp: () => {
          setPreviewDragActive(false);
        }
      };
    },
    onHeaderCell: () => ({
      onClick: () => selectWholeColumn(columnIndex),
      className: canDragSelectInPreview ? "preview-header-selectable" : undefined
    })
  }));

  const tableData = (preview?.rows ?? []).map((row, index) => {
    const item: PreviewTableRow = { key: `${index}` };
    (preview?.columns ?? []).forEach((column, columnIndex) => {
      item[column] = row[columnIndex] ?? "";
    });
    return item;
  });

  const sidebarItems = [
    {
      key: "preview",
      label: "Preview",
      children: preview ? (
        <div className="sidebar-panel preview-panel">
          <div className="preview-toolbar">
            <Space size={6}>
              <Button size="small" type={previewMode === "table" ? "primary" : "default"} onClick={() => setPreviewMode("table")}>
                Table
              </Button>
              <Button size="small" type={previewMode === "chart" ? "primary" : "default"} onClick={() => setPreviewMode("chart")}>
                Chart
              </Button>
              <Button size="small" type={previewMode === "split" ? "primary" : "default"} onClick={() => setPreviewMode("split")}>
                Split
              </Button>
            </Space>
            {previewSelection && (
              <Button
                size="small"
                onClick={() => {
                  setPreviewDragStart(null);
                  setPreviewDragEnd(null);
                }}
              >
                Clear Selection
              </Button>
            )}
          </div>

          {previewSelection && <Text className="preview-selection-label">Selection: {previewSelectedRangeText}</Text>}

          {activeConfirm && (
            <Text type="secondary" className="preview-drag-hint">
              Drag cells or click a column header to set the confirm field directly.
            </Text>
          )}

          {activeChartColumn && previewColumnMetrics[activeChartColumn] && (
            <div className="preview-metrics">
              <div className="preview-metric-card">
                <span>Column</span>
                <strong>{activeChartColumn}</strong>
              </div>
              <div className="preview-metric-card">
                <span>Count</span>
                <strong>{previewColumnMetrics[activeChartColumn].count}</strong>
              </div>
              <div className="preview-metric-card">
                <span>Avg</span>
                <strong>{formatMetric(previewColumnMetrics[activeChartColumn].avg)}</strong>
              </div>
              <div className="preview-metric-card">
                <span>Sum</span>
                <strong>{formatMetric(previewColumnMetrics[activeChartColumn].sum)}</strong>
              </div>
            </div>
          )}

          {(previewMode === "chart" || previewMode === "split") && (
            <div className="preview-chart-shell">
              {!chartPoints.length ? (
                <Text type="secondary">No numeric column available for chart preview.</Text>
              ) : (
                <>
                  <div className="preview-chart-title">
                    <Text strong>{activeChartColumn}</Text>
                    <Text type="secondary">
                      Range: {formatMetric(chartValueRange.min)} ~ {formatMetric(chartValueRange.max)}
                    </Text>
                  </div>
                  <div className="preview-chart">
                    {chartPoints.map((point) => {
                      const minBase = Math.min(0, chartValueRange.min);
                      const denominator = Math.max(1, chartValueRange.max - minBase);
                      const ratio = Math.max(0.04, (point.value - minBase) / denominator);
                      return (
                        <div className="preview-bar-item" key={`${point.rowIndex}-${point.label}`}>
                          <div className="preview-bar-track">
                            <div className="preview-bar-fill" style={{ height: `${Math.min(100, ratio * 100)}%` }} title={`${point.label}: ${point.value}`} />
                          </div>
                          <span className="preview-bar-label">{point.label}</span>
                          <span className="preview-bar-value">{formatMetric(point.value)}</span>
                        </div>
                      );
                    })}
                  </div>
                </>
              )}
            </div>
          )}

          {(previewMode === "table" || previewMode === "split") && (
            <Table
              pagination={false}
              columns={tableColumns}
              dataSource={tableData}
              size="small"
              scroll={{ x: true, y: previewMode === "split" ? 250 : 430 }}
              className={`preview-table${canDragSelectInPreview ? " preview-table-draggable" : ""}`}
            />
          )}
        </div>
      ) : (
        <div className="sidebar-panel">
          <Text type="secondary">Preview appears after node execution.</Text>
        </div>
      )
    },
    {
      key: "node",
      label: "Bubble",
      children: selectedNodeId === "goal" && workflow ? (
        <div className="sidebar-panel">
          <Space direction="vertical" style={{ width: "100%" }}>
            <Space>
              <Text strong>Goal</Text>
              <Tag color={workflow.status === "completed" ? "green" : "blue"}>{workflow.status}</Tag>
            </Space>
            <pre className="json-view">{JSON.stringify(workflow.parsed_goal, null, 2)}</pre>
          </Space>
        </div>
      ) : selectedNode ? (
        <div className="sidebar-panel">
          <Space direction="vertical" style={{ width: "100%" }}>
            <Space>
              <Text strong>{NODE_LABELS[selectedNode.type] ?? selectedNode.type}</Text>
              <Tag color={selectedNode.status === "success" ? "green" : selectedNode.status === "failed" ? "red" : "blue"}>
                {statusText(selectedNode.status)}
              </Tag>
            </Space>
            <pre className="json-view">{JSON.stringify(selectedNode.parameters, null, 2)}</pre>
          </Space>
        </div>
      ) : (
        <div className="sidebar-panel">
          <Text type="secondary">Click a node in canvas for details.</Text>
        </div>
      )
    },
    {
      key: "events",
      label: "Logs",
      children: (
        <div className="sidebar-panel">
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
        </div>
      )
    }
  ];

  return (
    <div className={`app-shell${resizingSidebar ? " is-resizing-sidebar" : ""}`}>
      <header className="header-bar">
        <div className="header-main">
          <div>
            <Title level={3} style={{ margin: 0 }}>
              Intent Clarification Canvas
            </Title>
            <Text type="secondary">Only decisions that need your input appear on canvas. Drag bubbles freely.</Text>
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
              <Text type="secondary">Technical steps stay hidden unless the system needs your input.</Text>
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

          {sidebarCollapsed ? (
            <div className="sidebar-collapsed">
              <Button size="small" onClick={() => setSidebarCollapsed(false)}>
                Show Panel
              </Button>
            </div>
          ) : (
            <div className="right-pane" style={{ width: sidebarWidth }}>
              <button
                type="button"
                className="sidebar-resizer"
                onMouseDown={startSidebarResize}
                aria-label="Resize sidebar"
              />
              <aside className="right-sidebar">
                <div className="sidebar-toolbar">
                  <Button size="small" onClick={() => setSidebarCollapsed(true)}>
                    Hide
                  </Button>
                </div>
                <Tabs size="small" items={sidebarItems} />
              </aside>
            </div>
          )}
        </section>
      )}
    </div>
  );
}
