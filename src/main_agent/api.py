"""FastAPI application exposing the agent over HTTP."""

from __future__ import annotations

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from fastapi import Depends, FastAPI, HTTPException

from . import __version__, conversations, history
from .agent import build_agent
from .auth import make_auth_dependency
from .config import Settings, load_settings
from .mcp_registry import build_toolsets, load_registry
from .schemas import (
    ChatRequest,
    ChatResponse,
    ConversationDetailResponse,
    ConversationListResponse,
    ConversationSummary,
    DeleteResponse,
    HealthResponse,
    McpServerStatus,
    McpStatusResponse,
    StoredTurn,
    UsageInfo,
)


log = logging.getLogger("main_agent")


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: Settings = app.state.settings

    # History DB is opened once per process; SQLite in WAL mode is safe
    # for concurrent reads with serialized writes, which matches our load.
    hist_conn = history.connect(settings.history_db_path)
    history.migrate(hist_conn)
    app.state.hist_conn = hist_conn

    specs = load_registry(settings.mcp_config_path)
    toolsets = build_toolsets(specs)
    agent = build_agent(settings, toolsets)

    app.state.agent = agent
    app.state.mcp_specs = specs
    log.info(
        "main_agent ready: model=%s mcp_servers=%s history_db=%s",
        settings.glm_model,
        [s.name for s in specs if s.enabled],
        settings.history_db_path,
    )

    async with agent:
        try:
            yield
        finally:
            hist_conn.close()


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
        conn = app.state.hist_conn

        conv_id = req.conversation_id
        if conv_id:
            if not conversations.exists(conn, conv_id):
                raise HTTPException(status_code=404, detail=f"conversation {conv_id} not found")
            past = conversations.load_history(conn, conv_id)
            if len(past) > settings.history_replay_limit:
                past = past[-settings.history_replay_limit :]
        else:
            conv_id = conversations.create_conversation(conn)
            past = []

        try:
            result = await asyncio.wait_for(
                agent.run(req.message, message_history=past),
                timeout=settings.request_timeout_s,
            )
        except asyncio.TimeoutError:
            raise HTTPException(status_code=504, detail="agent timeout")
        except Exception as exc:  # noqa: BLE001
            log.exception("agent.run failed")
            raise HTTPException(status_code=500, detail=f"agent error: {exc}")

        conversations.append_messages(
            conn,
            conv_id=conv_id,
            new_messages_json=result.new_messages_json(),
        )
        # First-turn title backfill — whatever the user said, truncated.
        conversations.set_title_if_missing(conn, conv_id=conv_id, title=req.message)

        usage = _extract_usage(result)
        tool_calls = _count_tool_calls(result)
        return ChatResponse(
            reply=str(result.output),
            model=settings.glm_model,
            conversation_id=conv_id,
            usage=usage,
            tool_calls=tool_calls,
        )

    @app.get(
        "/conversations",
        response_model=ConversationListResponse,
        dependencies=[Depends(auth_dep)],
    )
    async def list_conversations(limit: int = 50, offset: int = 0) -> ConversationListResponse:
        conn = app.state.hist_conn
        convs = conversations.list_conversations(conn, limit=limit, offset=offset)
        return ConversationListResponse(
            conversations=[ConversationSummary(**c.to_dict()) for c in convs],
        )

    @app.get(
        "/conversations/{conv_id}",
        response_model=ConversationDetailResponse,
        dependencies=[Depends(auth_dep)],
    )
    async def get_conversation(conv_id: str) -> ConversationDetailResponse:
        conn = app.state.hist_conn
        summary = conversations.get_conversation_summary(conn, conv_id)
        if summary is None:
            raise HTTPException(status_code=404, detail="conversation not found")

        stored = conversations.get_messages(conn, conv_id=conv_id)
        turns: list[StoredTurn] = []
        for row in stored:
            parts_list = _parts_from_blob(row.data)
            role, text = _summarize_message(parts_list)
            turns.append(
                StoredTurn(id=row.id, ts=row.ts, role=role, text=text, parts=parts_list)
            )

        return ConversationDetailResponse(
            id=summary.id,
            title=summary.title,
            created_at=summary.created_at,
            updated_at=summary.updated_at,
            messages=turns,
        )

    @app.delete(
        "/conversations/{conv_id}",
        response_model=DeleteResponse,
        dependencies=[Depends(auth_dep)],
    )
    async def delete_conversation(conv_id: str) -> DeleteResponse:
        conn = app.state.hist_conn
        deleted = conversations.delete_conversation(conn, conv_id)
        return DeleteResponse(deleted=deleted)

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


def _parts_from_blob(data: str) -> list[dict[str, Any]]:
    """Best-effort extraction of the `parts` array from a stored ModelMessage row.

    We keep the full serialized JSON so forward-compatibility isn't hurt by
    SDK bumps; we surface a simplified view for /conversations/{id} readers.
    """
    try:
        decoded = json.loads(data)
    except json.JSONDecodeError:
        return []
    if isinstance(decoded, list) and decoded:
        first = decoded[0]
        if isinstance(first, dict):
            parts = first.get("parts") or []
            if isinstance(parts, list):
                return parts
    return []


def _summarize_message(parts: list[dict[str, Any]]) -> tuple[str, str]:
    """Pull (role, text) out of a ModelMessage's parts list for UI display."""
    role = "unknown"
    texts: list[str] = []
    for p in parts:
        kind = p.get("part_kind") or p.get("type")
        if kind == "user-prompt":
            role = "user"
            content = p.get("content")
            if isinstance(content, str):
                texts.append(content)
        elif kind == "text":
            role = "assistant"
            content = p.get("content")
            if isinstance(content, str):
                texts.append(content)
        elif kind == "system-prompt":
            role = "system"
        elif kind == "tool-call":
            role = "assistant"
            name = p.get("tool_name", "?")
            texts.append(f"[tool_call: {name}]")
        elif kind == "tool-return":
            role = "tool"
            name = p.get("tool_name", "?")
            texts.append(f"[tool_return: {name}]")
    return role, "\n".join(texts).strip()
