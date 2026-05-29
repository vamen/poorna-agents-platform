"""Pydantic schemas for AgentDefinition — mirrors _generic_agent.yaml schema."""

from __future__ import annotations

from typing import Any, Optional, Union

from pydantic import BaseModel, Field, field_validator, model_validator

# ── Constants ────────────────────────────────────────────────────────────────

VALID_PROVIDERS = {"openai", "anthropic", "google", "azure", "ollama"}
VALID_STRATEGIES = {"predict", "cot", "react"}
VALID_TOOLS = {
    "http_request",
    "send_email",
    "send_telegram",
    "post_to_twitter",
    "get_file",
    "extract_json_field",
    "render_template",
}
VALID_MCP_SERVERS = {
    "gmail",
}
VALID_SCHEMA_TYPES = {"json", "string"}


# ── Event schemas ────────────────────────────────────────────────────────────

class EventPayload(BaseModel):
    event_schema_type: str
    value: Optional[Union[dict[str, str], str]] = None

    @field_validator("event_schema_type")
    @classmethod
    def valid_schema_type(cls, v: str) -> str:
        if v not in VALID_SCHEMA_TYPES:
            raise ValueError(f"event_schema_type must be one of {sorted(VALID_SCHEMA_TYPES)}")
        return v

    @model_validator(mode="after")
    def value_required_for_json(self) -> "EventPayload":
        if self.event_schema_type == "json" and not self.value:
            raise ValueError("value is required when event_schema_type is 'json'")
        return self


class EventSchema(BaseModel):
    name: str = Field(..., pattern=r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)*$")
    payload: EventPayload


# ── Model entries ─────────────────────────────────────────────────────────────

class ModelEntry(BaseModel):
    """One model in the fallback chain."""
    provider: str
    name: str

    @field_validator("provider")
    @classmethod
    def valid_provider(cls, v: str) -> str:
        if v not in VALID_PROVIDERS:
            raise ValueError(f"provider must be one of {sorted(VALID_PROVIDERS)}")
        return v


class ModelEntryResponse(BaseModel):
    """Model entry as returned to clients."""
    provider: str
    name: str


# ── Prompt ───────────────────────────────────────────────────────────────────

class PromptSchema(BaseModel):
    system: str = Field(..., min_length=1)
    user: str = Field(..., min_length=1)


# ── Reasoning ────────────────────────────────────────────────────────────────

class ReasoningCreate(BaseModel):
    strategy: str
    max_iterations: Optional[int] = Field(default=None, ge=1, le=50)
    model: list[ModelEntry] = Field(..., min_length=1)
    prompt: PromptSchema
    tools: list[str] = []
    mcp_servers: list[str] = []
    context_messages: int = Field(default=0, ge=0, le=100)

    @field_validator("strategy")
    @classmethod
    def valid_strategy(cls, v: str) -> str:
        if v not in VALID_STRATEGIES:
            raise ValueError(f"strategy must be one of {sorted(VALID_STRATEGIES)}")
        return v

    @field_validator("tools")
    @classmethod
    def valid_tools(cls, v: list[str]) -> list[str]:
        invalid = set(v) - VALID_TOOLS
        if invalid:
            raise ValueError(f"Unknown tools: {sorted(invalid)}. Valid: {sorted(VALID_TOOLS)}")
        return v

    @field_validator("mcp_servers")
    @classmethod
    def valid_mcp_servers(cls, v: list[str]) -> list[str]:
        invalid = set(v) - VALID_MCP_SERVERS
        if invalid:
            raise ValueError(f"Unknown MCP servers: {sorted(invalid)}. Valid: {sorted(VALID_MCP_SERVERS)}")
        return v

    @model_validator(mode="after")
    def react_requires_max_iterations(self) -> "ReasoningCreate":
        if self.strategy == "react" and self.max_iterations is None:
            self.max_iterations = 10   # sensible default
        return self


class ReasoningResponse(BaseModel):
    strategy: str
    max_iterations: Optional[int] = None
    model: list[ModelEntryResponse]
    prompt: PromptSchema
    tools: list[str]
    mcp_servers: list[str] = []
    context_messages: int = 0


# ── Top-level definition ──────────────────────────────────────────────────────

class AgentDefinitionCreate(BaseModel):
    name: str = Field(..., pattern=r"^[a-z][a-z0-9_]*$")
    display_name: str = Field(..., min_length=1)
    description: Optional[str] = None
    is_long_running: bool = False
    reasoning: ReasoningCreate
    events: list[EventSchema] = Field(..., min_length=1)

    def to_definition_dict(self) -> dict[str, Any]:
        """Serialise to the JSON blob stored in AgentDefinition.definition.

        api_key values ARE included here — they live in the blob (Phase 1).
        They are stripped from responses via AgentDefinitionResponse.
        """
        return self.model_dump(exclude_none=False)


class AgentDefinitionUpdate(BaseModel):
    """All fields optional for PATCH semantics."""
    display_name: Optional[str] = None
    description: Optional[str] = None
    is_long_running: Optional[bool] = None
    reasoning: Optional[ReasoningCreate] = None
    events: Optional[list[EventSchema]] = None


class AgentDefinitionResponse(BaseModel):
    id: str
    org_id: str
    name: str
    display_name: str
    description: Optional[str]
    is_long_running: bool
    reasoning: ReasoningResponse
    events: list[EventSchema]
    created_by: str
    updated_by: Optional[str]
    created_at: str
    updated_at: Optional[str]

    @classmethod
    def from_orm(cls, obj: Any) -> "AgentDefinitionResponse":
        """Build response from an AgentDefinition ORM row.

        Reads the definition blob and strips api_key from every model entry,
        replacing it with has_api_key: bool.
        """
        defn: dict = obj.definition

        reasoning_raw = defn["reasoning"]
        model_responses = [
            ModelEntryResponse(
                provider=m["provider"],
                name=m["name"],
            )
            for m in reasoning_raw["model"]
        ]
        reasoning_resp = ReasoningResponse(
            strategy=reasoning_raw["strategy"],
            max_iterations=reasoning_raw.get("max_iterations"),
            model=model_responses,
            prompt=PromptSchema(**reasoning_raw["prompt"]),
            tools=reasoning_raw.get("tools", []),
            mcp_servers=reasoning_raw.get("mcp_servers", []),
            context_messages=reasoning_raw.get("context_messages", 0),
        )

        events = [EventSchema(**e) for e in defn["events"]]

        return cls(
            id=obj.id,
            org_id=obj.org_id,
            name=obj.name,
            display_name=defn["display_name"],
            description=defn.get("description"),
            is_long_running=defn.get("is_long_running", False),
            reasoning=reasoning_resp,
            events=events,
            created_by=obj.created_by,
            updated_by=obj.updated_by,
            created_at=obj.created_at.isoformat() if obj.created_at else "",
            updated_at=obj.updated_at.isoformat() if obj.updated_at else None,
        )
