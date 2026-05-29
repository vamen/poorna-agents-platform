# Agent Platform

Workflow orchestration platform for chaining AI agents. Build multi-step automations on a visual canvas — agents communicate via events, runs are tracked live in the Runs Monitor.

## What's working

- **Visual workflow canvas** — drag-and-drop React Flow editor, connect agents with typed events
- **Custom agent definitions** — define agents (ReAct / Predict strategies) with live JSON preview
- **Temporal-backed execution** — each deployed workflow runs as a Temporal workflow, surviving restarts
- **Runs Monitor** — live SSE feed of every agent message as it happens
- **Built-in agents** — Telegram Watcher, Gmail Watcher, Classifier, API Caller
- **Custom agents** — define any agent via the UI; supports tool use (ReAct loop) with direct provider calls
- **Tool integrations** — Telegram (send), Twitter/X (post), Gmail, HTTP, filesystem
- **OAuth flows** — Google (Gmail) and Twitter OAuth 2.0 PKCE, tokens stored per-agent
- **Conversation history** — cross-session context stitched by chat_id for multi-turn Telegram bots

## Architecture

```
frontend (React + Vite)
    └── backend (FastAPI + SQLite)
            ├── Temporal worker  ← runs workflow graphs
            ├── Agents           ← built-in + custom (GenericAgent)
            └── Tools            ← Telegram, Twitter, Gmail, HTTP ...
```

## Setup

### 1. Prerequisites

- Python 3.12 + [uv](https://github.com/astral-sh/uv)
- Node.js 18+
- [Temporal CLI](https://docs.temporal.io/cli) — `brew install temporal`

### 2. Environment files

**Backend:**
```bash
cp backend/.env.example backend/.env
# Fill in the values — see backend/.env.example for descriptions
```

**Frontend:**
```bash
cp frontend/.env.example frontend/.env
# Defaults work for local development, no changes needed
```

### 3. Backend

```bash
cd backend
uv venv --python 3.12
uv pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

### 4. Frontend

```bash
cd frontend
npm install
npm run dev
```

### 5. Temporal (required for workflow execution)

```bash
temporal server start-dev
```

### 6. Temporal worker (required for workflow execution)

```bash
cd backend
python -m runtime.worker
```

App is available at **http://localhost:5173**

---

## Environment variables

### `backend/.env`

| Variable | Required | Description |
|---|---|---|
| `DATABASE_URL` | No | SQLite by default. Use `postgresql+asyncpg://...` for Postgres. |
| `ANTHROPIC_API_KEY` | Yes | Platform fallback key. Agents can also supply their own via the UI. |
| `TEMPORAL_HOST` | No | Defaults to `localhost:7233`. |
| `GOOGLE_CLIENT_ID` | For Gmail | OAuth 2.0 client from Google Cloud Console. |
| `GOOGLE_CLIENT_SECRET` | For Gmail | OAuth 2.0 secret. |
| `TWITTER_CLIENT_ID` | For X Poster | OAuth 2.0 client from Twitter Developer Portal. |
| `TWITTER_CLIENT_SECRET` | For X Poster | OAuth 2.0 secret. |
| `FRONTEND_URL` | No | Defaults to `http://localhost:5173`. Used for OAuth redirects. |
| `BETTER_AUTH_URL` | No | Defaults to `http://localhost:3000`. |
| `BETTER_AUTH_SECRET` | No | JWT signing secret. Change in production. |
| `FILE_BACKEND` | No | `local` (default) or `s3`. |

### `frontend/.env`

| Variable | Description |
|---|---|
| `VITE_API_URL` | Backend URL. Default: `http://localhost:8000` |
| `VITE_AUTH_URL` | Auth sidecar URL. Default: `http://localhost:3000` |

---

## Adding a Twitter / X Poster agent

1. Go to [developer.twitter.com](https://developer.twitter.com/) → create an app
2. Enable **OAuth 2.0**, set callback URL to `http://localhost:8000/auth/twitter/callback`
3. Required scopes: `tweet.read`, `tweet.write`, `users.read`, `offline.access`
4. Copy **Client ID** and **Client Secret** into `backend/.env`
5. In the platform UI: Agents → create an **X Poster** agent → connect Twitter via OAuth

## Adding a Gmail Watcher agent

1. Go to [Google Cloud Console](https://console.cloud.google.com/) → create a project
2. Enable the **Gmail API**
3. Create **OAuth 2.0 credentials** (Web application type)
4. Add `http://localhost:8000/auth/google/callback` as an authorised redirect URI
5. Copy **Client ID** and **Client Secret** into `backend/.env`
6. In the platform UI: Agents → create a **Gmail Watcher** agent → connect Google via OAuth

---

## .gitignore note

`.env` files containing secrets are gitignored. Only `.env.example` files are committed.
