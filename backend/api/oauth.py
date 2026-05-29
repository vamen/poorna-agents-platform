"""OAuth integration endpoints.

Supports platform-owned OAuth apps (Option A): one app per provider,
tokens stored per-agent in ``agent_tool_configs``.

Google (OAuth 2.0):
  1. Frontend calls GET /api/oauth/google/authorize?agent_id=<id>&tool_name=gmail
  2. Frontend redirects browser to the returned auth_url.
  3. Google redirects to GET /auth/gmail/callback?code=...&state=...
  4. Backend exchanges code for tokens, stores in agent_tool_configs, redirects back.

Twitter (OAuth 2.0 + PKCE):
  1. Frontend calls GET /api/oauth/twitter/authorize?agent_id=<id>&tool_name=post_to_twitter
  2. Backend generates code_verifier/challenge, stashes verifier, returns auth_url.
  3. Frontend redirects browser to twitter.com/i/oauth2/authorize.
  4. Twitter redirects to GET /auth/twitter/callback?code=...&state=...
  5. Backend exchanges code+verifier for tokens, stores in agent_tool_configs, redirects back.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import secrets
import time
import urllib.parse
from uuid import uuid4

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_current_user, get_db
from config import settings
from db.models import AgentToolConfig

logger = logging.getLogger(__name__)

api_router = APIRouter(prefix="/api/oauth", tags=["oauth"])
auth_router = APIRouter(prefix="/auth", tags=["oauth-callback"])

_TWITTER_PKCE_STORE: dict[str, tuple[str, str, float]] = {}
# keyed by state; value is (code_verifier, state_json, created_at)
_TWITTER_TOKEN_TTL = 600  # seconds

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"

TWITTER_AUTH_URL = "https://x.com/i/oauth2/authorize"
TWITTER_TOKEN_URL = "https://api.twitter.com/2/oauth2/token"
TWITTER_REDIRECT_URI = "http://localhost:8000/auth/twitter/callback"
TWITTER_SCOPES = "tweet.read tweet.write users.read offline.access"

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


# ── Twitter OAuth 2.0 + PKCE ──────────────────────────────────────────────────

def _pkce_pair() -> tuple[str, str]:
    """Return (code_verifier, code_challenge) using S256 method."""
    verifier = secrets.token_urlsafe(43)
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return verifier, challenge


@api_router.get("/twitter/authorize")
async def twitter_authorize(
    agent_id: str = Query(...),
    tool_name: str = Query(...),
    current_user: dict = Depends(get_current_user),
) -> dict:
    """Return the Twitter OAuth 2.0 consent URL (PKCE flow)."""
    if not settings.twitter_client_id:
        raise HTTPException(
            status_code=501,
            detail="Twitter OAuth is not configured (TWITTER_CLIENT_ID missing)",
        )

    state = secrets.token_urlsafe(16)
    state_payload = json.dumps({
        "agent_id": agent_id,
        "tool_name": tool_name,
        "user_id": current_user["id"],
    })

    code_verifier, code_challenge = _pkce_pair()
    # Stash verifier keyed by state
    _TWITTER_PKCE_STORE[state] = (code_verifier, state_payload, time.time())

    params = {
        "response_type": "code",
        "client_id": settings.twitter_client_id,
        "redirect_uri": TWITTER_REDIRECT_URI,
        "scope": TWITTER_SCOPES,
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    auth_url = f"{TWITTER_AUTH_URL}?{urllib.parse.urlencode(params)}"
    return {"auth_url": auth_url}


@auth_router.get("/twitter/callback")
async def twitter_callback(
    code: str = Query(default=None),
    state: str = Query(default=None),
    error: str = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    """Exchange the auth code for tokens and store in agent_tool_configs."""
    if error:
        return RedirectResponse(
            url=f"{settings.frontend_url}/workspace/agents?oauth_error={urllib.parse.quote(error)}"
        )

    if not code or not state:
        return RedirectResponse(
            url=f"{settings.frontend_url}/workspace/agents?oauth_error=missing_twitter_params"
        )

    stored = _TWITTER_PKCE_STORE.pop(state, None)
    if not stored:
        return RedirectResponse(
            url=f"{settings.frontend_url}/workspace/agents?oauth_error=twitter_state_expired"
        )

    code_verifier, state_payload, created_at = stored
    if time.time() - created_at > _TWITTER_TOKEN_TTL:
        return RedirectResponse(
            url=f"{settings.frontend_url}/workspace/agents?oauth_error=twitter_state_expired"
        )

    try:
        state_data = json.loads(state_payload)
        agent_id = state_data["agent_id"]
        tool_name = state_data["tool_name"]
    except (json.JSONDecodeError, KeyError) as exc:
        logger.error("Twitter callback bad state: %s", exc)
        return RedirectResponse(
            url=f"{settings.frontend_url}/workspace/agents?oauth_error=bad_state"
        )

    # Exchange code + verifier for tokens
    basic = base64.b64encode(
        f"{settings.twitter_client_id}:{settings.twitter_client_secret}".encode()
    ).decode()

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                TWITTER_TOKEN_URL,
                headers={
                    "Authorization": f"Basic {basic}",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": TWITTER_REDIRECT_URI,
                    "code_verifier": code_verifier,
                },
            )
            resp.raise_for_status()
            token_data = resp.json()
    except Exception as exc:
        logger.error("Twitter token exchange failed: %s", exc)
        return RedirectResponse(
            url=f"{settings.frontend_url}/workspace/agents/{agent_id}?oauth_error=twitter_token_failed"
        )

    # Fetch Twitter username
    username = ""
    try:
        async with httpx.AsyncClient() as client:
            me = await client.get(
                "https://api.twitter.com/2/users/me",
                headers={"Authorization": f"Bearer {token_data['access_token']}"},
            )
            me.raise_for_status()
            username = me.json().get("data", {}).get("username", "")
    except Exception as exc:
        logger.warning("Could not fetch Twitter username: %s", exc)

    credential = {
        "credential_type": "oauth2",
        "access_token": token_data["access_token"],
        "refresh_token": token_data.get("refresh_token", ""),
        "token_url": TWITTER_TOKEN_URL,
        "client_id": settings.twitter_client_id,
        "client_secret": settings.twitter_client_secret,
        "username": username,
    }

    config_blob = {"credential": credential}

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
            kind="tool",
            config=config_blob,
        ))
    await db.commit()

    logger.info(
        "Twitter connected: agent=%s tool=%s username=@%s",
        agent_id[:8], tool_name, username,
    )
    return RedirectResponse(
        url=f"{settings.frontend_url}/workspace/agents/{agent_id}?connected={urllib.parse.quote(tool_name)}"
    )


# ── Legacy alias: /api/oauth/callback ─────────────────────────────────────────

@api_router.get("/callback")
async def oauth_callback_legacy(
    code: str = Query(default=None),
    state: str = Query(default=None),
    error: str = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    return await _handle_callback(code, state, error, db)
