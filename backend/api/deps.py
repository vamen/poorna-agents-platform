from fastapi import Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from db.base import get_db


async def get_current_user(authorization: str = Header(default="")) -> dict:
    """Phase 1: extract user info from Bearer token (mock).
    Phase 2: validate JWT from Better Auth sidecar."""
    if not authorization.startswith("Bearer "):
        # For Phase 1 dev convenience, allow unauthenticated with defaults
        return {"id": "dev-user-id", "org_id": "dev-org-id"}

    token = authorization.replace("Bearer ", "")
    # Phase 1 mock: any token accepted, decode as "dev"
    if token == "dev":
        return {"id": "dev-user-id", "org_id": "dev-org-id"}

    # Basic JWT parsing (no verification in Phase 1)
    try:
        import base64
        import json
        parts = token.split(".")
        if len(parts) == 3:
            padded = parts[1] + "=" * (4 - len(parts[1]) % 4)
            payload = json.loads(base64.urlsafe_b64decode(padded))
            return {
                "id": payload.get("sub", "dev-user-id"),
                "org_id": payload.get("org_id", "dev-org-id"),
            }
    except Exception:
        pass

    return {"id": "dev-user-id", "org_id": "dev-org-id"}
