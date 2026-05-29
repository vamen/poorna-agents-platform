"""LiteLLM virtual key management.

Creates and stores per-agent virtual keys via the LiteLLM proxy API.
Keys are persisted in agents.litellm_virtual_key so they survive proxy restarts.
"""

from __future__ import annotations

import logging

import httpx

from config import settings

logger = logging.getLogger(__name__)


async def create_virtual_key(
    agent_id: str,
    agent_name: str,
    api_key: str = "",
) -> str:
    """Generate a LiteLLM virtual key for an agent and return it.

    If *api_key* is supplied it is stored as ``config.override_params.api_key``
    on the virtual key.  LiteLLM will then forward that key to the upstream
    provider (OpenAI, Anthropic, etc.) for every call made with this virtual key,
    instead of using the proxy-level provider key.
    """
    body: dict = {
        "key_alias": f"agent-{agent_id[:8]}",
        "metadata": {
            "agent_id": agent_id,
            "agent_name": agent_name,
        },
    }
    if api_key:
        body["config"] = {"override_params": {"api_key": api_key}}

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            f"{settings.litellm_base_url}/key/generate",
            headers={"Authorization": f"Bearer {settings.litellm_master_key}"},
            json=body,
        )
        resp.raise_for_status()
        key = resp.json()["key"]
        logger.info(
            "Created LiteLLM virtual key for agent %s (client key: %s)",
            agent_id[:8], "yes" if api_key else "no",
        )
        return key


async def delete_virtual_key(key: str) -> None:
    """Revoke a LiteLLM virtual key."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"{settings.litellm_base_url}/key/delete",
                headers={"Authorization": f"Bearer {settings.litellm_master_key}"},
                json={"keys": [key]},
            )
            resp.raise_for_status()
    except Exception as exc:
        logger.warning("Failed to delete LiteLLM key: %s", exc)
