# AI Agent Orchestration Platform

Phase 1 — fully local, zero cloud dependencies.

## Quick Start

### Option A: Docker Compose (all services)

```bash
cp .env.example .env
docker compose up --build
```

- Frontend: http://localhost:5173
- Backend API: http://localhost:8000
- Auth sidecar: http://localhost:3000
- API docs: http://localhost:8000/docs

### Option B: Local development

**Backend:**
```bash
cd backend
uv venv --python 3.12
uv pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

**Frontend:**
```bash
cd frontend
npm install
npm run dev
```

**Auth sidecar:**
```bash
cd auth
npm install
npm run dev
```

## Architecture

```
frontend (React + Vite)  →  backend (FastAPI)  →  SQLite
                         →  auth sidecar (Better Auth)
```

## What's built (Phase 1)

- **Workflow canvas** — drag & drop React Flow editor with custom nodes and labeled edges
- **Agent library** — create/manage agents from YAML-defined templates
- **Session monitor** — live SSE event stream from workflow executions  
- **4 agent templates** — Gmail Watcher, Telegram Gateway, Classifier, API Caller
- **2 workflow templates** — HR Resume Screener, Payment Reconciler
- **Full CRUD API** — agents, workflows, sessions with Pydantic validation
- **Alembic migrations** — schema-managed SQLite (swap to Postgres via env var)
- **Phase 2 stubs** — compiler, Temporal client, LangGraph runner (all return mock data)

## Phase 2 (future)

- Swap `DATABASE_URL` from sqlite to postgres
- Wire `runtime/temporal_client.py` to Temporal Cloud
- Wire `runtime/langgraph_runner.py` to LangGraph execution  
- Replace SSE polling with Redis pub/sub
- Add AWS Secrets Manager via `secret_ref` on agents
