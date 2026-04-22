"""FastAPI application exposing the agent over HTTP."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import Depends, FastAPI, HTTPException

from . import __version__
from .agent import build_agent
from .auth import make_auth_dependency
from .config import Settings, load_settings
from .mcp_registry import build_toolsets, load_registry
from .schemas import (
    ChatRequest,
    ChatResponse,
    HealthResponse,
    McpServerStatus,
    McpStatusResponse,
    UsageInfo,
)


log = logging.getLogger("main_agent")


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: Settings = app.state.settings
    specs = load_registry(settings.mcp_config_path)
    toolsets = build_toolsets(specs)
    agent = build_agent(settings, toolsets)

    app.state.agent = agent
    app.state.mcp_specs = specs
    log.info(
        "main_agent ready: model=%s mcp_servers=%s",
        settings.glm_model,
        [s.name for s in specs if s.enabled],
    )

    async with agent:
        yield


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()
    auth_dep = make_auth_dependency(settings)

    app = FastAPI(
        title="serverino main_agent",
        version=__version__,
        lifespan=_lifespan,
    )
    app.state.settings = settings

    @app.get("/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        return HealthResponse(version=__version__)

    @app.get("/mcp/status", response_model=McpStatusResponse, dependencies=[Depends(auth_dep)])
    async def mcp_status() -> McpStatusResponse:
        specs = app.state.mcp_specs
        return McpStatusResponse(
            servers=[
                McpServerStatus(
                    name=s.name,
                    url=s.url,
                    enabled=s.enabled,
                    authenticated=s.token is not None,
                )
                for s in specs
            ]
        )

    @app.post("/chat", response_model=ChatResponse, dependencies=[Depends(auth_dep)])
    async def chat(req: ChatRequest) -> ChatResponse:
        agent = app.state.agent
        try:
            result = await asyncio.wait_for(
                agent.run(req.message),
                timeout=settings.request_timeout_s,
            )
        except asyncio.TimeoutError:
            raise HTTPException(status_code=504, detail="agent timeout")
        except Exception as exc:  # noqa: BLE001
            log.exception("agent.run failed")
            raise HTTPException(status_code=500, detail=f"agent error: {exc}")

        usage = _extract_usage(result)
        tool_calls = _count_tool_calls(result)
        return ChatResponse(
            reply=str(result.output),
            model=settings.glm_model,
            usage=usage,
            tool_calls=tool_calls,
        )

    return app


def _extract_usage(result) -> UsageInfo | None:
    try:
        u = result.usage()
    except Exception:  # noqa: BLE001
        return None
    if u is None:
        return None
    return UsageInfo(
        input_tokens=getattr(u, "input_tokens", None) or getattr(u, "request_tokens", None),
        output_tokens=getattr(u, "output_tokens", None) or getattr(u, "response_tokens", None),
        total_tokens=getattr(u, "total_tokens", None),
    )


def _count_tool_calls(result) -> int:
    try:
        messages = result.all_messages()
    except Exception:  # noqa: BLE001
        return 0
    count = 0
    for msg in messages:
        parts = getattr(msg, "parts", []) or []
        for part in parts:
            if part.__class__.__name__ == "ToolCallPart":
                count += 1
    return count
