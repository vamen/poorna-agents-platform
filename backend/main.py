from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api import agents, agent_definitions, sessions, stream, workflows
import api.tools as tools_api
import api.oauth as oauth_api
from db.base import init_db, AsyncSessionLocal
from services.template_service import load_templates
from services.agent_definition_service import load_all_into_registry
from services.tool_registry_service import tool_registry


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    load_templates()
    tool_registry.load()
    # Load user-defined agent types from DB into the runtime registry
    async with AsyncSessionLocal() as db:
        await load_all_into_registry(db)
    yield


app = FastAPI(title="Agent Orchestration Platform", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000", "http://localhost:8000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(agents.router)
app.include_router(agent_definitions.router)
app.include_router(workflows.router)
app.include_router(sessions.router)
app.include_router(stream.router)
app.include_router(tools_api.router)
app.include_router(oauth_api.api_router)
app.include_router(oauth_api.auth_router)


@app.get("/health")
async def health():
    return {"status": "ok"}
