import asyncio
import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_current_user
from db.base import AsyncSessionLocal
from db.models import AgentMessage, WorkflowSession

router = APIRouter(prefix="/api/sessions", tags=["stream"])


async def event_generator(session_id: str):
    last_message_id = None
    keepalive_counter = 0

    while True:
        async with AsyncSessionLocal() as db:
            # Verify session exists
            result = await db.execute(
                select(WorkflowSession).where(WorkflowSession.id == session_id)
            )
            session = result.scalar_one_or_none()
            if not session:
                yield f"event: error\ndata: {json.dumps({'error': 'Session not found'})}\n\n"
                return

            # Stream new messages
            query = select(AgentMessage).where(AgentMessage.session_id == session_id)
            if last_message_id:
                subq = select(AgentMessage.created_at).where(AgentMessage.id == last_message_id).scalar_subquery()
                query = query.where(AgentMessage.created_at > subq)
            query = query.order_by(AgentMessage.created_at)

            msg_result = await db.execute(query)
            messages = msg_result.scalars().all()

            for msg in messages:
                data = {
                    "from_agent_id": msg.from_agent_id,
                    "to_agent_id": msg.to_agent_id,
                    "event_name": msg.event_name,
                    "payload": msg.payload,
                    "created_at": msg.created_at.isoformat() if msg.created_at else None,
                }
                yield f"event: agent_message\ndata: {json.dumps(data)}\n\n"
                last_message_id = msg.id

            # Emit session status if ended
            if session.status in ("completed", "failed"):
                data = {
                    "status": session.status,
                    "ended_at": session.ended_at.isoformat() if session.ended_at else None,
                }
                yield f"event: session_status\ndata: {json.dumps(data)}\n\n"
                return

        keepalive_counter += 1
        if keepalive_counter >= 15:  # every 30s
            yield f"event: keepalive\ndata: {{}}\n\n"
            keepalive_counter = 0

        await asyncio.sleep(2)


@router.get("/{session_id}/stream")
async def stream_session(
    session_id: str,
    current_user: dict = Depends(get_current_user),
):
    return StreamingResponse(
        event_generator(session_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
