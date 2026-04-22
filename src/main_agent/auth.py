"""Optional bearer-token dependency for protected endpoints."""

from __future__ import annotations

from fastapi import Header, HTTPException, status

from .config import Settings


def make_auth_dependency(settings: Settings):
    """Return a FastAPI dependency that enforces the bearer token when configured.

    Auth is disabled when `settings.api_key` is falsy — covers both the
    unset case (None) and the "variable present but empty" case (""),
    which is what Dockploy / docker-compose produce when the operator
    deletes the value but leaves the key in the env list.
    """

    expected = (settings.api_key or "").strip()
    if not expected:
        async def _noop() -> None:
            return None
        return _noop

    expected_header = f"Bearer {expected}"

    async def _verify(authorization: str | None = Header(default=None)) -> None:
        if authorization != expected_header:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="unauthorized",
                headers={"WWW-Authenticate": "Bearer"},
            )

    return _verify
