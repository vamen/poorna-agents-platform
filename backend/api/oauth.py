"""OAuth integration endpoints.

Supports platform-owned OAuth apps (Option A): one Google Cloud project,
tokens stored per-agent in ``agent_tool_configs``.

Flow:
  1. Frontend calls GET /api/oauth/google/authorize?agent_id=<id>&tool_name=gmail
  2. Frontend redirects browser to the returned auth_url.
  3. Google redirects to GET /auth/gmail/callback?code=...&state=...
     (registered redirect URI in Google Cloud Console)
  4. Backend exchanges code for tokens, stores in agent_tool_configs, redirects
     browser back to the frontend agent detail page.
"""

from __future__ import annotations

import json
import logging
import urllib.parse
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_current_user, get_db
from config import settings
from db.models import AgentToolConfig

logger = logging.getLogger(__name__)

# Two routers:
#   api_router  → /api/oauth  (the authorize helper used by frontend)
#   auth_router → /auth       (the bare redirect URI registered with Google)
api_router = APIRouter(prefix="/api/oauth", tags=["oauth"])
auth_router = APIRouter(prefix="/auth", tags=["oauth-callback"])

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"

GOOGLE_SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.modify",
]

# The redirect URI registered in Google Cloud Console
GOOGLE_REDIRECT_URI = "http://localhost:8000/auth/gmail/callback"


# ── Authorize ─────────────────────────────────────────────────────────────────

@api_router.get("/google/authorize")
async def google_authorize(
    agent_id: str = Query(...),
    tool_name: str = Query(...),
    current_user: dict = Depends(get_current_user),
) -> dict:
    """Return the Google OAuth consent URL for the frontend to redirect to."""
    if not settings.google_client_id:
        raise HTTPException(
            status_code=501,
            detail="Google OAuth is not configured (GOOGLE_CLIENT_ID missing)",
        )

    state = json.dumps({
        "agent_id": agent_id,
        "tool_name": tool_name,
        "user_id": current_user["id"],
    })

    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": " ".join(GOOGLE_SCOPES),
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    }
    auth_url = f"{GOOGLE_AUTH_URL}?{urllib.parse.urlencode(params)}"
    return {"auth_url": auth_url}


# ── Shared callback logic ──────────────────────────────────────────────────────

async def _handle_callback(
    code: str | None,
    state: str | None,
    error: str | None,
    db: AsyncSession,
) -> RedirectResponse:
    if error:
        logger.warning("OAuth callback error: %s", error)
        return RedirectResponse(
            url=f"{settings.frontend_url}/workspace/agents?oauth_error={urllib.parse.quote(error)}"
        )

    if not code or not state:
        return RedirectResponse(
            url=f"{settings.frontend_url}/workspace/agents?oauth_error=missing_code_or_state"
        )

    try:
        state_data = json.loads(state)
        agent_id = state_data["agent_id"]
        tool_name = state_data["tool_name"]
    except (json.JSONDecodeError, KeyError) as exc:
        logger.error("OAuth callback bad state: %s", exc)
        return RedirectResponse(
            url=f"{settings.frontend_url}/workspace/agents?oauth_error=bad_state"
        )

    # Exchange code → tokens
    import httpx
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                GOOGLE_TOKEN_URL,
                data={
                    "code": code,
                    "client_id": settings.google_client_id,
                    "client_secret": settings.google_client_secret,
                    "redirect_uri": GOOGLE_REDIRECT_URI,
                    "grant_type": "authorization_code",
                },
            )
            resp.raise_for_status()
            token_data = resp.json()
    except Exception as exc:
        logger.error("Token exchange failed: %s", exc)
        return RedirectResponse(
            url=f"{settings.frontend_url}/workspace/agents/{agent_id}?oauth_error=token_exchange_failed"
        )

    # Fetch Gmail address
    gmail_address = ""
    try:
        async with httpx.AsyncClient() as client:
            ui = await client.get(
                "https://www.googleapis.com/oauth2/v2/userinfo",
                headers={"Authorization": f"Bearer {token_data.get('access_token', '')}"},
            )
            ui.raise_for_status()
            gmail_address = ui.json().get("email", "")
    except Exception as exc:
        logger.warning("Could not fetch userinfo: %s", exc)

    credential = {
        "credential_type": "oauth2",
        "access_token": token_data.get("access_token", ""),
        "refresh_token": token_data.get("refresh_token", ""),
        "token_uri": GOOGLE_TOKEN_URL,
        "client_id": settings.google_client_id,
        "client_secret": settings.google_client_secret,
    }

    config_blob = {"gmail_address": gmail_address, "credential": credential}

    result = await db.execute(
        select(AgentToolConfig).where(
            AgentToolConfig.agent_id == agent_id,
            AgentToolConfig.name == tool_name,
        )
    )
    existing = result.scalar_one_or_none()
    if existing:
        existing.config = config_blob
    else:
        db.add(AgentToolConfig(
            id=str(uuid4()),
            agent_id=agent_id,
            name=tool_name,
            kind="mcp_server",
            config=config_blob,
        ))
    await db.commit()

    return RedirectResponse(
        url=f"{settings.frontend_url}/workspace/agents/{agent_id}?connected={urllib.parse.quote(tool_name)}"
    )


# ── Registered redirect URI: /auth/gmail/callback ─────────────────────────────

@auth_router.get("/gmail/callback")
async def gmail_callback(
    code: str = Query(default=None),
    state: str = Query(default=None),
    error: str = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    return await _handle_callback(code, state, error, db)


# ── Legacy alias: /api/oauth/callback ─────────────────────────────────────────

@api_router.get("/callback")
async def oauth_callback_legacy(
    code: str = Query(default=None),
    state: str = Query(default=None),
    error: str = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    return await _handle_callback(code, state, error, db)
