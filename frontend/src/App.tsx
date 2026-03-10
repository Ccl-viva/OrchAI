import { useMemo, useState } from "react";
import { Alert, Button, Card, Col, Input, message, Modal, Row, Select, Space, Table, Tag, Typography, Upload } from "antd";
import type { UploadProps } from "antd";
import ReactFlow, { Background, Controls, type Edge, type Node } from "reactflow";

import { createTask, executeWorkflow, uploadTaskFile } from "./api";
import type { ExecuteEvent, PendingConfirmation, PreviewData, WorkflowData } from "./types";

const { Title, Text } = Typography;

const NODE_LABELS: Record<string, string> = {
  upload_file: "Upload",
  parse_excel: "Parse",
  user_confirm: "Confirm",
  aggregate: "Aggregate",
  export_excel: "Export"
};

const STATUS_COLORS: Record<string, string> = {
  pending: "#7f8c9a",
  success: "#21b34b",
  failed: "#de3d3d",
  running: "#0a7aff",
  waiting: "#ff9f1a"
};

function statusColor(status: string): string {
  return STATUS_COLORS[status] ?? "#7f8c9a";
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

export default function App() {
  const [goal, setGoal] = useState("从 Excel 表中汇总价格总和");
  const [workflow, setWorkflow] = useState<WorkflowData | null>(null);
  const [events, setEvents] = useState<ExecuteEvent[]>([]);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [pendingConfirm, setPendingConfirm] = useState<PendingConfirmation | null>(null);
  const [confirmValue, setConfirmValue] = useState<string>("");
  const [submitting, setSubmitting] = useState(false);
  const [creatingTask, setCreatingTask] = useState(false);
  const [runningWorkflow, setRunningWorkflow] = useState(false);

  const apiBase = import.meta.env.VITE_API_BASE ?? "http://localhost:8000";
  const preview = useMemo(() => findLatestPreview(events, workflow), [events, workflow]);

  const flowNodes = useMemo<Node[]>(() => {
    if (!workflow) {
      return [];
    }
    return workflow.nodes
      .slice()
      .sort((a, b) => a.order_index - b.order_index)
      .map((node, index) => ({
        id: node.id,
        type: "default",
        position: { x: 90 + ((index + 1) % 2) * 280, y: 60 + index * 120 },
        data: { label: `${index + 1}. ${NODE_LABELS[node.type] ?? node.type}` },
        style: {
          border: `2px solid ${statusColor(node.status)}`,
          borderRadius: 14,
          color: "#11253a",
          background: "#ffffff",
          width: 220,
          fontWeight: 700
        }
      }));
  }, [workflow]);

  const flowEdges = useMemo<Edge[]>(() => {
    if (!workflow) {
      return [];
    }
    const ordered = workflow.nodes.slice().sort((a, b) => a.order_index - b.order_index);
    const edges: Edge[] = [];
    for (let i = 0; i < ordered.length - 1; i += 1) {
      edges.push({
        id: `${ordered[i].id}-${ordered[i + 1].id}`,
        source: ordered[i].id,
        target: ordered[i + 1].id,
        animated: ordered[i].status === "success" && ordered[i + 1].status === "pending",
        style: { stroke: "#5b6f88", strokeWidth: 2 }
      });
    }
    return edges;
  }, [workflow]);

  const selectedNode = useMemo(() => {
    if (!workflow || !selectedNodeId) {
      return null;
    }
    return workflow.nodes.find((node) => node.id === selectedNodeId) ?? null;
  }, [workflow, selectedNodeId]);

  async function handleCreateTask() {
    if (!goal.trim()) {
      message.error("请先输入目标。");
      return;
    }
    setCreatingTask(true);
    try {
      const data = await createTask(goal.trim());
      setWorkflow(data.workflow);
      setEvents([]);
      setSelectedNodeId(null);
      setPendingConfirm(null);
      setConfirmValue("");
      message.success("任务创建成功。");
    } catch (error) {
      message.error(`任务创建失败：${String(error)}`);
    } finally {
      setCreatingTask(false);
    }
  }

  const uploadProps: UploadProps = {
    maxCount: 1,
    showUploadList: true,
    customRequest: async (options) => {
      if (!workflow) {
        message.error("请先创建任务。");
        options.onError?.(new Error("Workflow not created"));
        return;
      }
      try {
        const file = options.file as File;
        const result = await uploadTaskFile(workflow.id, file);
        setWorkflow(result.workflow);
        message.success("文件上传成功。");
        options.onSuccess?.(result, options.file);
      } catch (error) {
        message.error(`上传失败：${String(error)}`);
        options.onError?.(new Error(String(error)));
      }
    }
  };

  async function runWorkflow(confirm?: string) {
    if (!workflow) {
      message.error("请先创建任务。");
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
        message.info("流程在确认节点暂停。");
      } else if (result.workflow.status === "completed") {
        message.success("流程执行完成。");
      } else {
        message.success("已执行当前可运行节点。");
      }
    } catch (error) {
      message.error(`执行失败：${String(error)}`);
    } finally {
      setRunningWorkflow(false);
    }
  }

  async function submitConfirmation() {
    if (!confirmValue) {
      message.error("请选择字段。");
      return;
    }
    setSubmitting(true);
    try {
      await runWorkflow(confirmValue);
      setPendingConfirm(null);
    } finally {
      setSubmitting(false);
    }
  }

  const tableColumns = (preview?.columns ?? []).map((column) => ({
    title: column,
    dataIndex: column,
    key: column
  }));

  const tableData = (preview?.rows ?? []).map((row, index) => {
    const item: Record<string, string | number> = {};
    (preview?.columns ?? []).forEach((column, idx) => {
      item[column] = row[idx] ?? "";
    });
    return { key: `${index}`, ...item };
  });

  return (
    <div className="app-shell">
      <div className="app-gradient" />
      <header className="app-header">
        <Title level={2} style={{ margin: 0 }}>
          Goal-Driven AI Workflow Demo
        </Title>
        <Text type="secondary">输入目标后自动规划并逐节点执行，关键节点由你确认。</Text>
      </header>

      <Row gutter={[16, 16]}>
        <Col xs={24} lg={10}>
          <Card className="panel-card" title="1) Goal Input">
            <Space direction="vertical" style={{ width: "100%" }} size={16}>
              <Input.TextArea
                value={goal}
                onChange={(event) => setGoal(event.target.value)}
                rows={4}
                placeholder="例如：从 Excel 表中汇总价格总和"
              />
              <Space wrap>
                <Button type="primary" onClick={handleCreateTask} loading={creatingTask}>
                  创建任务
                </Button>
                <Upload {...uploadProps} disabled={!workflow}>
                  <Button disabled={!workflow}>上传 Excel</Button>
                </Upload>
                <Button onClick={() => runWorkflow()} loading={runningWorkflow} type="default" disabled={!workflow}>
                  执行流程
                </Button>
              </Space>
              {workflow && (
                <Alert
                  type="info"
                  showIcon
                  message={`Workflow ID: ${workflow.id}`}
                  description={`状态: ${workflow.status}`}
                />
              )}
            </Space>
          </Card>

          <Card className="panel-card" title="4) Node Config Panel" style={{ marginTop: 16 }}>
            {!selectedNode ? (
              <Text type="secondary">点击流程画布中的节点查看参数。</Text>
            ) : (
              <Space direction="vertical" style={{ width: "100%" }}>
                <Text strong>{NODE_LABELS[selectedNode.type] ?? selectedNode.type}</Text>
                <Tag color="blue">{selectedNode.status}</Tag>
                <pre className="json-view">{JSON.stringify(selectedNode.parameters, null, 2)}</pre>
              </Space>
            )}
          </Card>
        </Col>

        <Col xs={24} lg={14}>
          <Card className="panel-card" title="2) Workflow Canvas">
            <div className="flow-wrap">
              {workflow ? (
                <ReactFlow
                  nodes={flowNodes}
                  edges={flowEdges}
                  fitView
                  onNodeClick={(_, node) => setSelectedNodeId(node.id)}
                >
                  <Background color="#dde5ef" gap={16} />
                  <Controls />
                </ReactFlow>
              ) : (
                <Text type="secondary">创建任务后显示流程。</Text>
              )}
            </div>
          </Card>

          <Card className="panel-card" title="3) Data Preview" style={{ marginTop: 16 }}>
            {preview ? (
              <Table pagination={false} columns={tableColumns} dataSource={tableData} scroll={{ x: true }} size="small" />
            ) : (
              <Text type="secondary">节点执行后会显示实时预览。</Text>
            )}
          </Card>

          <Card className="panel-card" title="Execution Events" style={{ marginTop: 16 }}>
            <div className="event-list">
              {events.length === 0 ? (
                <Text type="secondary">暂无执行记录。</Text>
              ) : (
                events.map((event, index) => (
                  <div className="event-item" key={`${event.node_id}-${index}`}>
                    <Tag color={event.status === "success" ? "green" : event.status === "failed" ? "red" : "orange"}>
                      {event.node_type}
                    </Tag>
                    <Text>{event.message}</Text>
                  </div>
                ))
              )}
            </div>
            {workflow?.status === "completed" && (
              <div style={{ marginTop: 12 }}>
                <Button type="link" href={`${apiBase}/task/download/${workflow.id}`} target="_blank">
                  下载导出结果
                </Button>
              </div>
            )}
          </Card>
        </Col>
      </Row>

      <Modal
        title="确认字段"
        open={Boolean(pendingConfirm)}
        onCancel={() => setPendingConfirm(null)}
        onOk={submitConfirmation}
        okText="确认并继续"
        confirmLoading={submitting}
      >
        <Space direction="vertical" style={{ width: "100%" }}>
          <Text>{pendingConfirm?.message}</Text>
          <Select
            style={{ width: "100%" }}
            value={confirmValue}
            onChange={(value) => setConfirmValue(value)}
            options={(pendingConfirm?.options ?? []).map((value) => ({ value, label: value }))}
          />
        </Space>
      </Modal>
    </div>
  );
}
