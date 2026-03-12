# OrchAI

**An intent-clarification AI system that turns vague goals into stable results.**  
**一个将模糊需求逐步收敛为稳定结果的 AI 意图澄清系统。**

## What Is OrchAI? | OrchAI 是什么

### English
OrchAI is not another generic workflow builder.

It is an **AI intent convergence system**:

- users describe a goal in natural language
- AI fills in the hidden execution path
- the system only interrupts when critical ambiguity remains
- users clarify through focused bubbles
- the system continues automatically and produces a stable output

The product is designed for a very practical problem:

**most AI failures do not start with a weak model, but with an unclear request.**

OrchAI exists to reduce that ambiguity before it becomes a bad result.

### 中文
OrchAI 不是一个普通的流程图工具，也不是把一堆技术节点直接暴露给用户的工作流产品。

它的核心是一个 **AI 意图收敛系统**：

- 用户先用自然语言提出目标
- AI 自动补全隐藏的执行路径
- 只有在关键信息仍然模糊时，系统才打断用户
- 用户通过聚焦的澄清气泡补充信息
- 系统自动继续推进，并输出更稳定的结果

这个产品要解决的是一个非常真实的问题：

**很多 AI 结果不稳定，不是因为模型不够强，而是因为用户的需求在进入模型时仍然不够清晰。**

OrchAI 的价值就在于：在错误结果发生之前，先把用户意图收敛清楚。

## Why It Matters | 为什么这个方向有价值

### English
Users rarely speak in perfect prompts.

In real work, they say things like:

- "Help me summarize this sheet."
- "I want the price result."
- "Make it clearer."
- "Export something I can send."

Those requests are normal for humans, but dangerous for LLM systems.

OrchAI makes that interaction safer by:

- reducing ambiguity
- reducing rework
- increasing first-pass correctness
- making outputs easier to confirm and reuse

### 中文
大多数用户并不会一开始就写出精确、完整、结构化的 Prompt。

真实场景里的表达往往是这样的：

- “帮我汇总一下这个表”
- “我要价格结果”
- “帮我弄清楚一点”
- “导出一个可以发给别人的版本”

这对人来说很自然，但对 LLM 系统来说却很危险。

OrchAI 的作用就是把这种高风险的模糊表达变得更安全、更可控：

- 降低歧义
- 减少返工
- 提高第一次产出的正确率
- 让结果更容易确认、更容易复用

## What Makes OrchAI Different | OrchAI 的差异化特点

| Feature | English | 中文 |
| --- | --- | --- |
| Intent clarification first | The visible canvas shows only decisions that need user input, not low-level execution plumbing. | 可视画布只展示真正需要用户参与的澄清点，而不是底层技术流程。 |
| Hidden execution path | Parsing, aggregation, export, and other deterministic steps run automatically in the background. | 解析、聚合、导出等确定性步骤在后台自动执行，不强迫用户理解实现细节。 |
| Natural clarification bubbles | Users refine intent through focused conversation bubbles instead of learning workflow syntax. | 用户通过聚焦的澄清气泡进行修正，而不是学习复杂的流程配置语法。 |
| LLM understanding + deterministic execution | LLM handles understanding and clarification, while code handles execution for stability. | LLM 负责理解与澄清，代码负责执行，以保证稳定性。 |
| Spreadsheet-native interaction | Live preview, table/chart views, drag selection, and direct interaction make the system feel closer to the spreadsheet itself. | 实时预览、表格/图表切换、拖拽选择等能力让系统更接近 Excel 的原生使用体验。 |
| Extensible architecture | Excel-first today, adapter-based for CSV and future sources. | 当前以 Excel 为重点，同时通过适配器架构保留对 CSV 和其他系统的扩展能力。 |

## Product Flow | 产品流程

```text
User goal
-> AI interprets intent
-> Hidden technical steps are planned automatically
-> Clarification bubble appears only if required
-> User answers or adjusts the bubble
-> System continues automatically
-> Result preview updates
-> Exportable output is generated
```

对应中文：

```text
用户提出目标
-> AI 先理解意图
-> 自动补全隐藏的技术路径
-> 只有必要时才出现澄清气泡
-> 用户回答或修改气泡
-> 系统自动继续推进
-> 右侧结果实时预览
-> 最终生成可导出的结果
```

## Demo Highlights | 当前 Demo 能力

- Excel upload and parsing
- CSV upload and parsing
- Goal parsing with:
  - user-provided OpenAI API key
  - server-level OpenAI key
  - deterministic rule fallback
- Clarification bubbles for ambiguous choices
- Natural-language node chat for modifying intent
- Automatic hidden-step execution until clarification is needed
- Real-time preview with:
  - table mode
  - chart mode
  - split mode
  - drag-selection assistance for field confirmation
- Export to Excel or CSV

当前 Demo 已实现：

- Excel 上传与解析
- CSV 上传与解析
- 支持用户自己的 OpenAI API Key，也支持服务端默认 Key，若都没有则自动回退规则解析
- 模糊需求触发澄清气泡
- 用户可在澄清气泡中使用自然语言修改意图
- 后台自动跑完隐藏技术步骤，直到需要用户确认时才暂停
- 右侧支持表格、图表、分屏和拖拽选择等实时预览体验
- 支持导出 Excel 或 CSV

## Current Positioning | 当前产品定位

### English
OrchAI is currently positioned as an **Excel-first intent clarification system**.

That means:

- the interaction model is general
- the current product depth is focused on spreadsheet workflows
- the long-term opportunity is broader than Excel

The strategic direction is:

**start with spreadsheet-heavy workflows, validate intent convergence, then expand to more systems.**

### 中文
OrchAI 当前的定位是一个 **Excel-first 的 AI 意图澄清系统**。

这意味着：

- 交互模型本身是通用的
- 当前产品深度优先落在表格场景
- 长期机会并不止于 Excel

它的战略路径应该是：

**先在表格和报表类任务中验证“意图收敛”机制，再逐步扩展到更多系统。**

## Architecture | 架构概览

```text
Frontend
├── Goal entry
├── Clarification canvas
├── Spreadsheet preview
└── Side panel

Backend
├── Goal parser
├── Planner
├── Execution engine
├── Workflow state manager
└── LLM provider layer

Adapters
├── Excel adapter
└── CSV adapter
```

Project structure:

```text
OrchAI/
├── backend/
│   ├── app/
│   │   ├── adapters/
│   │   ├── llm/
│   │   ├── main.py
│   │   ├── db.py
│   │   ├── goal_parser.py
│   │   ├── execution.py
│   │   ├── planner.py
│   │   ├── csv_planner.py
│   │   ├── core_planner.py
│   │   ├── node_dialogue.py
│   │   └── schemas.py
│   ├── requirements.txt
│   └── storage/
│       ├── uploads/
│       └── exports/
├── frontend/
│   ├── src/
│   │   ├── App.tsx
│   │   ├── App.css
│   │   ├── api.ts
│   │   └── types.ts
│   └── package.json
└── README.md
```

## Quick Start | 快速开始

### Backend

```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Backend endpoints:

- API: `http://127.0.0.1:8000`
- Docs: `http://127.0.0.1:8000/docs`

### Frontend

```powershell
cd frontend
npm install
npm run dev -- --host 127.0.0.1 --port 5173
```

Frontend:

- App: `http://127.0.0.1:5173`

## Environment Variables | 环境变量

### Backend

- `OPENAI_API_KEY`
- `GOAL_PARSER_MODEL`  
  Default: `gpt-4.1-mini`
- `ORCHAI_DEFAULT_LLM_PROVIDER`  
  Current implementation: `openai`

### Frontend

- `VITE_API_BASE`  
  Default: `http://127.0.0.1:8000`

## LLM Usage | LLM 使用方式

### English
The current MVP supports three levels of LLM planning:

1. user session key
2. server environment key
3. rule fallback

User-provided keys are **not stored in plaintext in the database**.  
They are kept only in backend process memory for the active server session.

### 中文
当前 MVP 支持三层 LLM 使用方式：

1. 用户当前会话提供的 Key
2. 服务端环境变量提供的默认 Key
3. 若都没有，则自动回退到规则解析

用户提供的 Key **不会以明文形式写入数据库**，当前只保存在后端进程内存中。

## Core API | 核心接口

### Create task

```json
POST /task/create
{
  "goal": "sum price from excel",
  "llm": {
    "provider": "openai",
    "model": "gpt-4.1-mini",
    "api_key": "sk-..."
  }
}
```

### Upload file

```text
POST /task/upload
form-data:
- workflow_id
- file
```

### Execute workflow

```json
POST /workflow/execute
{
  "workflow_id": "...",
  "confirm_value": "price"
}
```

### Clarification chat

```json
POST /node/chat
{
  "workflow_id": "...",
  "node_id": "...",
  "message": "Use the price column and calculate the average."
}
```

### Read / download

- `GET /workflow/{workflow_id}`
- `GET /task/download/{workflow_id}`


## Roadmap | 路线图

- richer clarification types: field, sheet, range, output format
- stronger spreadsheet-native interaction
- reusable workflow templates
- more adapters beyond Excel and CSV
- multi-provider LLM support
- enterprise-grade key management and permissions

对应中文：

- 更丰富的澄清类型：字段、工作表、区域、输出格式
- 更强的表格原生交互体验
- 可复用模板沉淀
- 扩展到 Excel / CSV 之外的数据源
- 支持更多 LLM 提供商
- 企业级的 Key 管理与权限控制

## Status | 当前状态

This repository is an MVP focused on validating the product interaction model and the Excel-first user experience.  
该仓库当前仍处于 MVP 阶段，重点在于验证产品交互模型和 Excel-first 的用户体验方向。
