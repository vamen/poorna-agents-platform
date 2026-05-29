# Agent Platform — Backend Design

## Table of Contents

1. [Overview](#1-overview)
2. [Directory Structure](#2-directory-structure)
3. [Database Schema](#3-database-schema)
4. [Agent System](#4-agent-system)
5. [Standard Messaging](#5-standard-messaging)
6. [Temporal Workflow Runtime](#6-temporal-workflow-runtime)
7. [LLM Integration (LiteLLM)](#7-llm-integration-litellm)
8. [API Layer](#8-api-layer)
9. [Services](#9-services)
10. [End-to-End Flow: Resume Pipeline](#10-end-to-end-flow-resume-pipeline)
11. [Authentication & Multi-tenancy](#11-authentication--multi-tenancy)
12. [Phase 1 vs Phase 2](#12-phase-1-vs-phase-2)

---

## 1. Overview

The backend is a Python/FastAPI service that executes **workflow graphs** — directed graphs of agents connected by events. Each node in the graph is an agent (Gmail watcher, LLM classifier, PDF parser, email sender, etc.). Edges carry an event name and an optional Python filter expression.

Execution is driven by **Temporal.io**: a long-running workflow polls a trigger agent on a timer and routes events through downstream nodes. Every agent-to-agent message is persisted to the database via a `NodeWrapper` before the agent runs.

**Key technologies:**
- FastAPI — REST API
- SQLAlchemy (async) + SQLite (aiosqlite) — persistence
- Temporal.io — durable workflow execution
- Claude (via LiteLLM proxy) — LLM calls in agents
- Gmail API — trigger and action nodes
- pypdf — PDF text extraction

---

## 2. Directory Structure

```
backend/
├── agents/                     # Agent implementations
│   ├── base.py                 # BaseAgent ABC, _get_llm_client()
│   ├── standard_message.py     # StandardMessage dataclass
│   ├── node_wrapper.py         # NodeWrapper — persistence before agent.run()
│   ├── gmail_watcher.py        # Long-running trigger: polls Gmail
│   ├── classifier.py           # LLM-based email classifier
│   ├── pdf_parser.py           # PDF text extraction + LLM profile extraction
│   ├── assignment_generator.py # LLM-based take-home assignment generator
│   ├── gmail_sender.py         # Gmail API action: send/reply
│   └── __init__.py             # AGENT_REGISTRY, instantiate_agent()
│
├── api/                        # FastAPI route handlers
│   ├── agents.py               # /api/agents/*
│   ├── workflows.py            # /api/workflows/*
│   ├── sessions.py             # /api/sessions/*
│   ├── tools.py                # /api/tools/*, /api/agents/{id}/tool-configs/*
│   ├── agent_definitions.py    # /api/agent-definitions/*
│   ├── oauth.py                # Google OAuth flow
│   └── deps.py                 # get_db(), get_current_user()
│
├── db/
│   ├── base.py                 # AsyncSessionLocal, engine setup
│   ├── models.py               # SQLAlchemy ORM models
│   └── migrations/             # Alembic migration versions
│
├── runtime/
│   ├── workflow.py             # Temporal workflow + activities
│   ├── worker.py               # Temporal worker process entry point
│   ├── temporal_client.py      # start/pause/resume workflow helpers
│   ├── gmail_client.py         # Gmail API: list, get, send, attachment download
│   └── compiler.py             # Graph validation and compilation
│
├── services/
│   ├── agent_service.py
│   ├── workflow_service.py
│   ├── message_service.py      # Session + AgentMessage persistence
│   ├── agent_state_service.py  # Cursor state for long-running agents
│   ├── litellm_service.py      # Virtual key creation/deletion
│   ├── template_service.py     # YAML template registry
│   ├── agent_definition_service.py  # Custom agent type CRUD
│   └── tool_registry_service.py
│
├── schemas/                    # Pydantic request/response models
├── templates/                  # YAML agent type definitions (8 predefined)
├── tools/                      # Tool registry (gmail, http_request, …)
│   └── <name>/
│       ├── meta.yaml
│       ├── schema.yaml         # JSON Schema for credential form
│       └── ui.yaml             # UI hints (labels, placeholders)
│
├── scripts/
│   └── seed_resume_workflow.py # One-time seed for resume pipeline
│
├── config.py                   # Settings (env-driven via pydantic-settings)
├── main.py                     # FastAPI app, lifespan, CORS
├── litellm_config.yaml         # LiteLLM proxy model list + master key
└── requirements.txt
```

---

## 3. Database Schema

### 3.1 Entity Relationship

```
Workflow ──< Agent ──< AgentToolConfig
   │
   └──< WorkflowSession ──< AgentMessage
                                ├── from_agent_id → Agent
                                └── to_agent_id   → Agent

Agent ──< AgentState        (cursor state, keyed by workflow_id + key)
Org ──< AgentDefinition     (custom agent type definitions)
```

### 3.2 Table Definitions

#### `workflows`
| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `org_id` | string | multi-tenancy scope |
| `name` | string | |
| `template_slug` | string nullable | e.g. `resume_pipeline` |
| `graph_definition` | JSON | `{nodes, edges}` — React Flow format |
| `compiled_graph` | JSON nullable | output of `compile_graph()` |
| `temporal_workflow_id` | string nullable | running Temporal workflow ID |
| `litellm_virtual_key` | string nullable | per-workflow LLM proxy key |
| `status` | string | `draft` \| `active` \| `paused` |
| `created_by` | string | user ID |
| `created_at`, `updated_at` | datetime | |

#### `agents`
| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `org_id` | string | |
| `workflow_id` | UUID FK nullable | cascade delete |
| `name` | string | display name |
| `type` | string | matches agent template name |
| `config` | JSON | instance config (label_filter, company_name, …) |
| `secret_ref` | string nullable | Phase 2: AWS Secrets Manager ref |
| `is_active` | bool | |
| `created_by` | string | |
| `created_at`, `updated_at` | datetime | |

#### `agent_tool_configs`
| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `agent_id` | UUID FK | cascade delete |
| `name` | string | e.g. `gmail` |
| `kind` | string | `tool` \| `mcp_server` |
| `config` | JSON | OAuth credential blob |
| `created_at`, `updated_at` | datetime | |
| **Unique** | `(agent_id, name)` | one config per tool per agent |

#### `workflow_sessions`
| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | session_id / workflow_run_id |
| `workflow_id` | UUID FK | |
| `correlation_id` | string nullable | Gmail message_id; used for idempotency on replay |
| `trigger_event` | string | e.g. `gmail_watcher.email.received` |
| `trigger_payload` | JSON nullable | |
| `status` | string | `running` \| `completed` \| `failed` |
| `started_at` | datetime | |
| `ended_at` | datetime nullable | |

One session = one "run" through the workflow graph (one email processed end-to-end).

#### `agent_messages`
| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | = `StandardMessage.message_id` |
| `session_id` | UUID FK | → `workflow_sessions` |
| `from_agent_id` | UUID FK | → `agents` |
| `to_agent_id` | UUID FK | → `agents` |
| `event_name` | string | namespaced, e.g. `pdf_parser.resume.parsed` |
| `payload` | JSON | the event data |
| `status` | string | `pending` → `delivered` \| `failed` |
| `created_at` | datetime | |

#### `agent_state`
| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `agent_id` | string | not a FK — long-running agents survive workflow recreation |
| `workflow_id` | string | |
| `key` | string | e.g. `last_internal_date` |
| `value` | JSON | the stored value |
| `updated_at` | datetime | always refreshed on upsert |
| **Unique** | `(agent_id, workflow_id, key)` | |

#### `agent_definitions`
| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `org_id` | string | |
| `name` | string | agent type slug, unique within org |
| `definition` | JSON | full definition blob (conforms to `_generic_agent.yaml`) |
| `created_by`, `updated_by` | string | |
| `created_at`, `updated_at` | datetime | |

---

## 4. Agent System

### 4.1 BaseAgent

All agent types extend `BaseAgent` (agents/base.py):

```python
class BaseAgent(ABC):
    agent_type: ClassVar[str]

    def __init__(self, config: dict) -> None: ...

    @classmethod
    def emitted_events(cls) -> list[TemplateEvent]: ...  # from YAML template

    @classmethod
    def event_names(cls) -> list[str]: ...               # ["agent_type.event_name", ...]

    def _get_llm_client(self): ...                       # LiteLLM or direct Anthropic

    async def run(self, event_name: str, payload: dict) -> dict: ...
```

Every `run()` must return `{"event": "<namespaced_event>", "payload": {...}}`.

### 4.2 Agent Registry

`agents/__init__.py` maintains `AGENT_REGISTRY: dict[str, type[BaseAgent]]`. Populated at startup with all predefined types plus dynamically registered custom types from `AgentDefinition` rows in the DB.

```python
agent = instantiate_agent("pdf_parser", config)   # returns PdfParserAgent instance
```

### 4.3 Predefined Agent Types

#### `gmail_watcher` — Long-running trigger
- **Mode:** polling (called by Temporal every N seconds via `poll()`)
- **State:** `last_internal_date` (ms epoch) stored in `agent_state` — only fetches messages newer than cursor
- **Config:** `label_filter`, `sender_filter`, `subject_filter`, `has_attachment`, `filename_filter`, `poll_interval`
- **Tool config required:** Gmail OAuth credential
- **Emits:** `gmail_watcher.email.received`
  ```json
  {
    "message_id", "thread_id", "subject", "sender", "to",
    "body", "snippet", "attachments": [{"filename", "attachment_id", "mime_type", "size"}],
    "internal_date"
  }
  ```

#### `classifier` — LLM email classifier
- **Model:** `claude-haiku-4-5`
- **Config:** `categories: list[str]`, `criteria: str`
- **Emits:** `classifier.classification.done` `{category, confidence, reasoning, original_payload}`
- **Emits:** `classifier.classification.failed` `{reason, original_payload}`

#### `pdf_parser` — Resume PDF extractor
- **Models:** pypdf (text extraction) + `claude-haiku-4-5` (structured profile)
- **Tool config:** Gmail credential (to download attachments on demand)
- **Emits:** `pdf_parser.resume.parsed`
  ```json
  {
    "candidate_name", "candidate_email", "candidate_phone",
    "current_role", "current_company", "years_of_experience",
    "skills": [], "experience_summary", "raw_text", "original_payload"
  }
  ```
- **Emits:** `pdf_parser.parse.failed` `{reason, original_payload}`

#### `assignment_generator` — Take-home assignment creator
- **Model:** `claude-sonnet-4-5`
- **Config:** `company_name`, `role`
- **Emits:** `assignment_generator.assignment.ready`
  ```json
  { "to_email", "candidate_name", "subject", "assignment_text", "original_payload" }
  ```
- **Emits:** `assignment_generator.generation.failed`

#### `gmail_sender` — Gmail send/reply action
- **Tool config required:** Gmail OAuth credential
- **Config:** `forward_to` (fallback recipient; overridden by `payload.to_email`)
- **Threading:** recursively unwraps `original_payload` chain to find the root email's `thread_id`
- **Emits:** `gmail_sender.email.sent` `{to, subject, message_id}`
- **Emits:** `gmail_sender.email.failed` `{reason}`

#### `telegram_gateway`, `api_caller` — Phase 2 stubs
- Registered in registry with empty `run()` implementations.

### 4.4 Custom Agent Types (AgentDefinition)

Custom agents are defined via the API and stored in `agent_definitions`. At startup (and on creation), `agent_definition_service._register_in_runtime()` dynamically creates a subclass of `BaseAgent` using `make_generic_class()` and inserts it into `AGENT_REGISTRY` and the template registry. Custom agent `run()` is a no-op in Phase 1; Phase 2 will drive it with a LLM reasoning strategy.

---

## 5. Standard Messaging

All agent-to-agent communication passes through a `StandardMessage` envelope persisted before the agent runs.

### 5.1 StandardMessage

```python
@dataclass
class StandardMessage:
    session_id:    str   # WorkflowSession.id
    workflow_id:   str   # Workflow.id
    from_agent_id: str   # sender Agent.id
    to_agent_id:   str   # receiver Agent.id
    event_name:    str   # e.g. "pdf_parser.resume.parsed"
    payload:       dict  # raw event data
    message_id:    str   # auto UUID
```

### 5.2 NodeWrapper

`agents/node_wrapper.py` wraps any `BaseAgent`. It is the **only** place that writes to `agent_messages`.

```
NodeWrapper.run(message: StandardMessage) → dict

  1. save_message(message)          → agent_messages row (status="pending")
  2. agent.run(event_name, payload) → result dict
  3a. update_message_status("delivered")
  3b. on exception: update_message_status("failed"), re-raise
```

Designed to be reusable outside Temporal — the Telegram workflow will call `NodeWrapper.run()` directly.

### 5.3 Session lifecycle

```
trigger emits event
  → create_session_activity (idempotent on correlation_id)
      → WorkflowSession row (status="running")
  → all NodeWrapper calls in this run reference the same session_id
  → session can be marked "completed"/"failed" via close_session()
```

`correlation_id` = Gmail `message_id` for the resume pipeline. This prevents duplicate sessions if Temporal replays the activity.

---

## 6. Temporal Workflow Runtime

### 6.1 Topology

```
GraphWorkflow.run(GraphWorkflowInput)
│
└── while True:
    ├── poll_trigger_activity(PollInput)
    │     → GmailWatcher.poll(credential, last_internal_date)
    │     → updates agent_state cursor
    │     → returns [events]
    │
    └── for each event:
        ├── create_session_activity(CreateSessionInput) → session_id
        │
        └── _route_event(event, source_node, session_id, ...)  [workflow code]
             │
             └── for each matching outgoing edge:
                 ├── [event filter]   edge.data.event == event_name?
                 ├── [expr filter]    eval(edge.data.filter, payload)?
                 │
                 └── run_node_activity(RunNodeInput)
                       → NodeWrapper(agent).run(StandardMessage)
                       │   → save AgentMessage to DB
                       │   → agent.run(event_name, payload)
                       │   → update AgentMessage status
                       → RunNodeOutput(event_name, payload)
                       │
                       └── _route_event(output_event, ...)  [recurse]
```

### 6.2 Dataclasses (Temporal-serializable)

```python
GraphWorkflowInput:
  workflow_id, graph_definition, agent_db_configs, poll_interval, litellm_virtual_key

PollInput:
  agent_type, agent_config, tool_config, agent_id, workflow_id

PollOutput:
  events: list[dict]

CreateSessionInput:
  workflow_id, trigger_event, correlation_id

RunNodeInput:
  agent_type, agent_config, tool_config, event_name, payload,
  session_id, workflow_id, from_agent_id, to_agent_id, litellm_virtual_key

RunNodeOutput:
  event_name, payload
```

### 6.3 Activity Retry Policies

| Activity | Timeout | Retries |
|---|---|---|
| `poll_trigger_activity` | 120s | 3 |
| `create_session_activity` | 30s | 3 |
| `run_node_activity` | 60s | 2 |

Workflow execution timeout: 365 days.

### 6.4 Edge Routing

Edges carry:
- `event` — required event name (empty = match any)
- `filter` — optional Python expression evaluated with `payload` in scope

```python
# Example filter on a classifier → pdf_parser edge:
payload.get("category") == "resume"
```

`_route_event` fans out to **all** matching outgoing edges (parallel execution via Temporal task scheduling).

### 6.5 Cursor-based Polling

`GmailWatcher` never accumulates a `seen_ids` list. Instead:

1. Load `last_internal_date` (int, ms epoch) from `agent_state`.
2. Build Gmail query with `after:{last_internal_date // 1000}`.
3. Skip any messages where `internal_date <= last_internal_date` (boundary dedup).
4. After poll, save `max(event.payload.internal_date)` as new cursor.

This makes the poller O(1) in storage and correct across worker restarts.

---

## 7. LLM Integration (LiteLLM)

### 7.1 Architecture

```
Agent._get_llm_client()
  │
  ├── if _litellm_key in config:
  │     OpenAI(api_key=litellm_key, base_url="http://localhost:4000")
  │     → LiteLLM proxy → Anthropic API
  │
  └── else:
        OpenAI(api_key=anthropic_api_key, base_url="https://api.anthropic.com/v1")
        → Anthropic API (direct fallback)
```

LiteLLM proxy runs as a Docker container (see `docker-compose.litellm.yml`). Its PostgreSQL DB persists virtual keys across container restarts.

### 7.2 Virtual Key Lifecycle

```
deploy_workflow()
  → litellm_service.create_virtual_key(workflow_id, workflow_name)
      → POST /key/generate to LiteLLM proxy
      → returns sk-... key
  → stored in workflows.litellm_virtual_key

Temporal GraphWorkflowInput.litellm_virtual_key = key

run_node_activity injects:
  config["_litellm_key"] = inp.litellm_virtual_key

Agent calls _get_llm_client() → routes through proxy with that key
```

### 7.3 Models in Use

| Agent | Model | Purpose |
|---|---|---|
| `classifier` | `claude-haiku-4-5` | Email category classification |
| `pdf_parser` | `claude-haiku-4-5` | Structured profile extraction from resume text |
| `assignment_generator` | `claude-sonnet-4-5` | Tailored take-home assignment generation |

---

## 8. API Layer

### 8.1 Agents

| Method | Path | Description |
|---|---|---|
| GET | `/api/agents/templates` | List all agent type templates |
| GET | `/api/agents/templates/{type}` | Single template |
| GET | `/api/agents` | List agents (optional `?workflow_id=`) |
| POST | `/api/agents` | Create agent instance |
| GET | `/api/agents/{id}` | Get agent |
| PATCH | `/api/agents/{id}` | Update name/config |
| DELETE | `/api/agents/{id}` | Delete (soft) |
| GET | `/api/agents/{id}/events` | List emittable events |
| GET | `/api/agents/{id}/tool-configs` | List tool configs |
| PUT | `/api/agents/{id}/tool-configs/{name}` | Upsert tool config (credential) |
| DELETE | `/api/agents/{id}/tool-configs/{name}` | Remove tool config |

### 8.2 Workflows

| Method | Path | Description |
|---|---|---|
| GET | `/api/workflows/templates` | List workflow templates |
| GET | `/api/workflows/templates/{slug}` | Single template |
| GET | `/api/workflows` | List workflows |
| POST | `/api/workflows` | Create draft |
| GET | `/api/workflows/{id}` | Get workflow |
| PATCH | `/api/workflows/{id}` | Update graph (draft only) |
| DELETE | `/api/workflows/{id}` | Delete (draft only) |
| GET | `/api/workflows/{id}/sessions` | List run sessions |
| POST | `/api/workflows/{id}/validate` | Validate graph |
| POST | `/api/workflows/{id}/deploy` | Compile + start Temporal + create LiteLLM key |
| POST | `/api/workflows/{id}/pause` | Cancel Temporal workflow |
| POST | `/api/workflows/{id}/resume` | Re-deploy |

### 8.3 Sessions & Messages

| Method | Path | Description |
|---|---|---|
| GET | `/api/sessions/{id}` | Session detail |
| GET | `/api/sessions/{id}/messages` | All AgentMessages for a session |
| POST | `/api/sessions` | Create session directly (for non-Temporal use) |

### 8.4 Tools

| Method | Path | Description |
|---|---|---|
| GET | `/api/tools` | List registered tools |
| GET | `/api/tools/{name}/schema` | JSON Schema for credential form |
| GET | `/api/tools/{name}/ui` | UI hints |

### 8.5 Agent Definitions (Custom Types)

| Method | Path | Description |
|---|---|---|
| GET | `/api/agent-definitions` | List custom agent types |
| POST | `/api/agent-definitions` | Create custom type |
| GET | `/api/agent-definitions/{id}` | Get definition |
| PATCH | `/api/agent-definitions/{id}` | Update definition |
| DELETE | `/api/agent-definitions/{id}` | Delete |
| GET | `/api/agent-definitions/schema` | Generic agent YAML schema |
| GET | `/api/agent-definitions/tools` | Tool descriptors |

---

## 9. Services

### `workflow_service.py`

Core business logic for workflow lifecycle:

- `deploy_workflow()` — validates graph → compiles → builds `agent_db_configs` map → creates LiteLLM virtual key → starts Temporal workflow → stores `temporal_workflow_id` in DB
- `_build_agent_db_configs()` — for each graph node, fetches `Agent.config` + `AgentToolConfig.config` (Gmail credential) and returns `{agent_db_id: {config, tool_config}}`
- `validate_workflow_graph()` — checks nodes have agents assigned and edge events are valid for source agent type
- `pause_workflow_action()` / `resume_workflow_action()` — cancels/re-deploys Temporal workflow

### `message_service.py`

Session and message persistence:

- `get_or_create_session(workflow_id, trigger_event, correlation_id)` — idempotent on `(workflow_id, correlation_id)`
- `save_message(message: StandardMessage)` — inserts `agent_messages` row with `status="pending"`
- `update_message_status(message_id, status)` — sets `delivered` or `failed`
- `close_session(session_id, status)` — marks session terminal

### `agent_state_service.py`

Key-value store for long-running agent cursor state. Uses raw SQL upserts so `updated_at` always advances even when the value is unchanged (SQLAlchemy ORM skips UPDATE for identical JSON).

### `litellm_service.py`

Thin HTTP client over LiteLLM proxy API:

- `create_virtual_key(workflow_id, workflow_name)` — `POST /key/generate`, tags key with workflow metadata
- `delete_virtual_key(key)` — `POST /key/delete`

### `template_service.py`

In-memory YAML template registry. Loaded at startup from `templates/*.yaml`. Also receives dynamic registrations from `agent_definition_service`. Used by `BaseAgent.emitted_events()` and graph validation.

### `agent_definition_service.py`

Manages custom agent types:
- `create_definition()` / `update_definition()` — persist to DB and call `_register_in_runtime()`
- `_register_in_runtime()` — uses `make_generic_class()` to synthesize a `BaseAgent` subclass at runtime, inserts into `AGENT_REGISTRY` and template registry
- `load_all_into_registry()` — called at startup to rehydrate all custom types

---

## 10. End-to-End Flow: Resume Pipeline

```
Graph: GmailWatcher → PdfParser → AssignmentGenerator → GmailSender
Edges: email.received → resume.parsed → assignment.ready
```

### Step 1 — Poll
Temporal timer fires → `poll_trigger_activity` → `GmailWatcher.poll(credential, last_internal_date)` → Gmail API query `label:INBOX has:attachment filename:pdf after:{ts}` → returns new emails.

### Step 2 — Session
`create_session_activity` → `get_or_create_session(workflow_id, "gmail_watcher.email.received", gmail_message_id)` → inserts `WorkflowSession` row → returns `session_id`.

### Step 3 — PDF Parser node
`run_node_activity`:
1. `NodeWrapper` builds `StandardMessage(from=watcher_id, to=parser_id, event="gmail_watcher.email.received", payload=email)`
2. Persists `AgentMessage` (status=pending)
3. `PdfParserAgent.run()` → downloads PDF bytes via Gmail API → extracts text with pypdf → calls Claude Haiku → returns structured profile
4. Updates `AgentMessage` status=delivered

### Step 4 — Assignment Generator node
`run_node_activity`:
1. `NodeWrapper` persists `AgentMessage(from=parser_id, to=gen_id, event="pdf_parser.resume.parsed")`
2. `AssignmentGeneratorAgent.run()` → calls Claude Sonnet with candidate profile → generates tailored assignment text
3. Emits `{to_email, candidate_name, subject, assignment_text, original_payload}`

### Step 5 — Gmail Sender node
`run_node_activity`:
1. `NodeWrapper` persists `AgentMessage(from=gen_id, to=sender_id, event="assignment_generator.assignment.ready")`
2. `GmailSenderAgent.run()` → extracts `to_email` from payload → unwraps `original_payload` chain to find root `thread_id` → calls Gmail API `send_message(..., reply_to_msg={thread_id})` → threads reply to original email
3. Emits `gmail_sender.email.sent`

### DB state after one email processed
```
workflow_sessions:   1 row  (correlation_id = Gmail message_id)
agent_messages:      3 rows (watcher→parser, parser→gen, gen→sender)
agent_state:         cursor advanced (last_internal_date = email's internalDate)
```

---

## 11. Authentication & Multi-tenancy

**Phase 1 (dev):** `get_current_user()` in `api/deps.py` accepts any Bearer token and returns `{user_id: "dev-user-id", org_id: "dev-org-id"}`. No JWT validation.

**Multi-tenancy:** Every user-scoped table has `org_id`. All list queries filter by `org_id`. Workflows, agents, definitions, and sessions are fully isolated per org.

**Gmail OAuth:** `api/oauth.py` implements the Google OAuth2 authorization code flow. After successful auth, the credential blob (access_token, refresh_token, client_id, client_secret, token_uri) is stored in `agent_tool_configs.config` for the relevant agent.

**Phase 2:** JWT validation against Better Auth sidecar; `secret_ref` in agents for AWS Secrets Manager credential storage.

---

## 12. Phase 1 vs Phase 2

| Feature | Phase 1 | Phase 2 |
|---|---|---|
| Database | SQLite | PostgreSQL |
| Auth | Mock bearer token | JWT via Better Auth |
| Credentials | Plain-text in DB JSON | AWS Secrets Manager via `secret_ref` |
| LLM routing | LiteLLM proxy + direct fallback | LiteLLM only + per-workflow budgets |
| Custom agents | Static event schema, no `run()` | LLM reasoning strategies |
| Telegram agent | Empty stub | python-telegram-bot polling |
| API caller agent | Empty stub | HTTP with auth/retry/transform |
| Graph execution | Sequential fan-out | True parallelism (concurrent Temporal activities) |
| Session close | Manual | Auto-close on terminal agent or timeout |
| Observability | Worker logs | OpenTelemetry traces per message |

---

## Appendix: Adding a New Agent Type

1. Create `agents/<name>.py` extending `BaseAgent`:
   ```python
   class MyAgent(BaseAgent):
       agent_type = "my_agent"
       async def run(self, event_name, payload) -> dict:
           return {"event": "my_agent.thing.done", "payload": {...}}
   ```

2. Register in `agents/__init__.py`:
   ```python
   from agents.my_agent import MyAgent
   AGENT_REGISTRY["my_agent"] = MyAgent
   ```

3. Create `templates/my_agent.yaml` with events, config fields, and tool requirements.

4. Optionally add a `tools/<tool_name>/` directory if the agent needs a new credential type.

That's it — the agent is immediately available in the graph builder, graph validator, and LLM client factory.
