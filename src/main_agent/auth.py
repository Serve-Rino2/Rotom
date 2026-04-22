"""Optional bearer-token dependency for protected endpoints."""

from __future__ import annotations

from fastapi import Header, HTTPException, status

from .config import Settings


def make_auth_dependency(settings: Settings):
    """Return a FastAPI dependency that enforces the bearer token when configured.

    When `settings.api_key` is None, the dependency is a no-op — the API is
    left open (acceptable on a trusted LAN).
    """

    expected = settings.api_key
    if expected is None:
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
