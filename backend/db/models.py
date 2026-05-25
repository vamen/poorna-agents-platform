from uuid import uuid4
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, JSON, String, UniqueConstraint
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from db.base import Base


class Agent(Base):
    __tablename__ = "agents"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    org_id = Column(String(36), nullable=False, index=True)
    # Optional FK — when set the agent belongs to a specific workflow canvas
    workflow_id = Column(String(36), ForeignKey("workflows.id", ondelete="CASCADE"), nullable=True, index=True)
    name = Column(String, nullable=False)
    type = Column(String, nullable=False)
    config = Column(JSON, nullable=False, default=dict)
    secret_ref = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    created_by = Column(String(36), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    sent_messages = relationship("AgentMessage", foreign_keys="AgentMessage.from_agent_id", back_populates="from_agent")
    received_messages = relationship("AgentMessage", foreign_keys="AgentMessage.to_agent_id", back_populates="to_agent")
    tool_configs = relationship("AgentToolConfig", back_populates="agent", cascade="all, delete-orphan")


class Workflow(Base):
    __tablename__ = "workflows"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    org_id = Column(String(36), nullable=False, index=True)
    name = Column(String, nullable=False)
    template_slug = Column(String, nullable=True)
    graph_definition = Column(JSON, nullable=False, default=dict)
    compiled_graph = Column(JSON, nullable=True)
    temporal_workflow_id = Column(String, nullable=True)
    status = Column(String, default="draft")
    created_by = Column(String(36), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    sessions = relationship("WorkflowSession", back_populates="workflow")


class WorkflowSession(Base):
    __tablename__ = "workflow_sessions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    workflow_id = Column(String(36), ForeignKey("workflows.id"), nullable=False)
    correlation_id = Column(String, nullable=True)
    trigger_event = Column(String, nullable=False)
    trigger_payload = Column(JSON, nullable=True)
    status = Column(String, default="running")
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    ended_at = Column(DateTime(timezone=True), nullable=True)

    workflow = relationship("Workflow", back_populates="sessions")
    messages = relationship("AgentMessage", back_populates="session")


class AgentDefinition(Base):
    """User-defined custom agent type.

    One row = one custom agent *type* (not an instance).
    The full definition is stored as a JSON blob in ``definition``,
    conforming to the schema in templates/_generic_agent.yaml.

    ``name`` mirrors ``definition['name']`` and is indexed for fast registry
    lookups. Together with ``org_id`` it forms a unique constraint — two
    different orgs may share the same agent name, but within one org names
    must be unique.
    """

    __tablename__ = "agent_definitions"
    __table_args__ = (
        UniqueConstraint("name", "org_id", name="uq_agent_def_name_org"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    org_id = Column(String(36), nullable=False, index=True)

    # Indexed mirror of definition['name'] for fast lookups and uniqueness.
    name = Column(String, nullable=False, index=True)

    # Full agent definition blob — conforms to _generic_agent.yaml schema.
    definition = Column(JSON, nullable=False)

    created_by = Column(String(36), nullable=False)
    updated_by = Column(String(36), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class AgentToolConfig(Base):
    """Per-agent credential/configuration for a tool or MCP server.

    One row = one configured tool for one agent *instance*.
    - ``name`` is the tool/server name (e.g. "gmail", "http_request").
    - ``kind`` is "tool" or "mcp_server".
    - ``config`` is a JSON blob conforming to tools/<name>/schema.yaml.
      Sensitive fields (tokens, keys) are stored plain-text in Phase 1.
      Phase 2: replace with secret_ref → AWS Secrets Manager.

    Unique constraint: (agent_id, name) — one config per tool per agent.
    """

    __tablename__ = "agent_tool_configs"
    __table_args__ = (
        UniqueConstraint("agent_id", "name", name="uq_agent_tool_config_agent_name"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    agent_id = Column(String(36), ForeignKey("agents.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String, nullable=False)          # e.g. "gmail", "http_request"
    kind = Column(String, nullable=False)           # "tool" | "mcp_server"
    config = Column(JSON, nullable=False)           # credential/config blob
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    agent = relationship("Agent", back_populates="tool_configs")


class AgentMessage(Base):
    __tablename__ = "agent_messages"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    session_id = Column(String(36), ForeignKey("workflow_sessions.id"), nullable=False)
    from_agent_id = Column(String(36), ForeignKey("agents.id"), nullable=False)
    to_agent_id = Column(String(36), ForeignKey("agents.id"), nullable=False)
    event_name = Column(String, nullable=False)
    payload = Column(JSON, nullable=True)
    status = Column(String, default="delivered")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    session = relationship("WorkflowSession", back_populates="messages")
    from_agent = relationship("Agent", foreign_keys=[from_agent_id], back_populates="sent_messages")
    to_agent = relationship("Agent", foreign_keys=[to_agent_id], back_populates="received_messages")
