# OrchAI - Goal-Driven AI Workflow Demo

这是一个可运行的 MVP，目标是验证以下链路：

`用户输入目标 -> 自动规划流程 -> 逐节点执行 -> 实时预览 -> 用户确认 -> 导出结果`

## 目录结构

```text
OrchAI/
├─ backend/
│  ├─ app/
│  │  ├─ main.py
│  │  ├─ db.py
│  │  ├─ planner.py
│  │  ├─ goal_parser.py
│  │  ├─ execution.py
│  │  └─ schemas.py
│  ├─ requirements.txt
│  └─ storage/
│     ├─ uploads/
│     └─ exports/
└─ frontend/
   ├─ src/
   │  ├─ App.tsx
   │  ├─ api.ts
   │  └─ types.ts
   └─ package.json
```

## 功能覆盖（Demo）

- Excel 上传
- 目标解析（LLM 可选，默认规则解析）
- 自动流程（Upload -> Parse -> Confirm -> Aggregate -> Export）
- 实时数据预览（表格）
- 用户确认字段后继续执行
- 导出 Excel 并下载

## 后端启动

```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

后端地址：`http://localhost:8000`

可选环境变量：

- `OPENAI_API_KEY`：配置后优先使用 OpenAI 解析目标
- `GOAL_PARSER_MODEL`：默认 `gpt-4.1-mini`

## 前端启动

```powershell
cd frontend
npm install
npm run dev
```

前端地址：`http://localhost:5173`

可选环境变量：

- `VITE_API_BASE`：默认 `http://localhost:8000`

## 核心 API

- `POST /task/create`
  - body: `{ "goal": "sum price from excel" }`
- `POST /task/upload`
  - form-data: `workflow_id`, `file`
- `POST /workflow/execute`
  - body: `{ "workflow_id": "...", "confirm_value": "price" }`
- `GET /workflow/{id}`
- `GET /task/download/{workflow_id}`

## Demo 使用步骤

1. 输入目标，例如：`从 Excel 表中汇总价格总和`
2. 点击 `创建任务`
3. 上传 Excel 文件
4. 点击 `执行流程`
5. 在弹窗中确认字段
6. 自动继续执行并生成导出文件
7. 点击下载结果
