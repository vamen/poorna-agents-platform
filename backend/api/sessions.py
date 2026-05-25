from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_current_user
from db.base import get_db
from db.models import AgentMessage, WorkflowSession
from schemas.session import MessageResponse, SessionCreate, SessionDetailResponse, SessionResponse

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


@router.get("/{session_id}", response_model=SessionDetailResponse)
async def get_session(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    result = await db.execute(select(WorkflowSession).where(WorkflowSession.id == session_id))
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    msg_result = await db.execute(
        select(AgentMessage)
        .where(AgentMessage.session_id == session_id)
        .order_by(AgentMessage.created_at)
    )
    messages = msg_result.scalars().all()

    return SessionDetailResponse(
        id=session.id,
        workflow_id=session.workflow_id,
        trigger_event=session.trigger_event,
        trigger_payload=session.trigger_payload,
        status=session.status,
        started_at=session.started_at,
        ended_at=session.ended_at,
        messages=[MessageResponse.model_validate(m) for m in messages],
    )


@router.get("/{session_id}/messages", response_model=list[MessageResponse])
async def list_messages(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    result = await db.execute(
        select(AgentMessage)
        .where(AgentMessage.session_id == session_id)
        .order_by(AgentMessage.created_at)
    )
    return result.scalars().all()


@router.post("", response_model=SessionResponse, status_code=201)
async def create_session(
    data: SessionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    session = WorkflowSession(
        workflow_id=data.workflow_id,
        trigger_event=data.trigger_event,
        trigger_payload=data.trigger_payload,
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session
