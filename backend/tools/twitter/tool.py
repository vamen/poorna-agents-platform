"""Twitter/X tool — posts a tweet using Twitter API v2 with OAuth 2.0 User Context.

Credentials expected in creds dict (stored by the OAuth callback):
  credential.access_token     = <user access token>
  credential.refresh_token    = <refresh token>
  credential.client_id        = <platform app client_id>
  credential.client_secret    = <platform app client_secret>
"""

from __future__ import annotations

import base64
import logging
from typing import Optional

import httpx

from tools.base import BaseTool

logger = logging.getLogger(__name__)

TWITTER_TWEET_URL = "https://api.twitter.com/2/tweets"
TWITTER_TOKEN_URL = "https://api.twitter.com/2/oauth2/token"


async def _refresh_access_token(
    client_id: str,
    client_secret: str,
    refresh_token: str,
) -> dict:
    """Exchange a refresh token for a new access + refresh token pair."""
    basic = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            TWITTER_TOKEN_URL,
            headers={
                "Authorization": f"Basic {basic}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            },
        )
        resp.raise_for_status()
        return resp.json()


async def _post_tweet(access_token: str, text: str, reply_to: Optional[str] = None) -> dict:
    """POST to Twitter API v2 /tweets using OAuth 2.0 Bearer token."""
    body: dict = {"text": text}
    if reply_to:
        body["reply"] = {"in_reply_to_tweet_id": reply_to}

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            TWITTER_TWEET_URL,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
            json=body,
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()


async def _save_tokens(agent_id: str, access_token: str, refresh_token: str, existing_cred: dict) -> None:
    """Persist rotated OAuth tokens back to agent_tool_configs so they're not lost."""
    if not agent_id:
        return
    try:
        import sqlalchemy as sa
        from db.base import AsyncSessionLocal
        from db.models import AgentToolConfig

        new_cred = {**existing_cred, "access_token": access_token, "refresh_token": refresh_token}
        async with AsyncSessionLocal() as db:
            res = await db.execute(
                sa.select(AgentToolConfig).where(
                    AgentToolConfig.agent_id == agent_id,
                    AgentToolConfig.name == "post_to_twitter",
                )
            )
            tc = res.scalar_one_or_none()
            if tc:
                tc.config = {"credential": new_cred}
                await db.commit()
                logger.info("TwitterTool: rotated tokens saved for agent %s", agent_id[:8])
    except Exception as exc:
        logger.warning("TwitterTool: failed to save rotated tokens: %s", exc)


class TwitterTool(BaseTool):
    name = "post_to_twitter"
    description = (
        "Post a tweet to Twitter/X on behalf of the authenticated user. "
        "Returns the tweet ID and URL on success."
    )
    input_schema = {
        "type": "object",
        "required": ["text"],
        "properties": {
            "text": {
                "type": "string",
                "description": "The text content of the tweet. Max 280 characters.",
            },
            "reply_to_tweet_id": {
                "type": "string",
                "description": "Optional. If set, posts this tweet as a reply.",
            },
        },
    }

    async def execute(self, input: dict, creds: dict) -> dict:
        c = creds.get("credential", creds)

        access_token: Optional[str] = c.get("access_token")
        refresh_token: Optional[str] = c.get("refresh_token")
        client_id: str = c.get("client_id", "")
        client_secret: str = c.get("client_secret", "")
        reply_to: Optional[str] = input.get("reply_to_tweet_id")

        if not access_token:
            raise ValueError("Twitter credential missing access_token — reconnect via OAuth")

        try:
            data = await _post_tweet(access_token, input["text"], reply_to)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in (401, 403) and refresh_token and client_id and client_secret:
                logger.info("TwitterTool: access token expired (HTTP %s), refreshing…", exc.response.status_code)
                try:
                    new_tokens = await _refresh_access_token(client_id, client_secret, refresh_token)
                    access_token = new_tokens["access_token"]
                    new_refresh = new_tokens.get("refresh_token", refresh_token)
                    # Persist rotated tokens immediately so they're not lost
                    await _save_tokens(
                        creds.get("_agent_id", ""),
                        access_token,
                        new_refresh,
                        c,  # full credential blob to preserve other fields
                    )
                    data = await _post_tweet(access_token, input["text"], reply_to)
                except Exception as refresh_exc:
                    raise RuntimeError(
                        f"Twitter post failed and token refresh also failed: {refresh_exc}"
                    ) from refresh_exc
            else:
                raise RuntimeError(
                    f"Twitter post failed: HTTP {exc.response.status_code} — {exc.response.text}"
                ) from exc

        tweet_id = data.get("data", {}).get("id", "")
        logger.info("TwitterTool: posted tweet id=%s", tweet_id)
        return {
            "tweet_id": tweet_id,
            "url": f"https://twitter.com/i/web/status/{tweet_id}",
        }


tool = TwitterTool()
