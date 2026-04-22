"""Request / response Pydantic models exposed by the HTTP API."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, description="The new user message")
    conversation_id: str | None = Field(
        default=None,
        description=(
            "Opaque id to thread messages together. If omitted, the server "
            "creates a new conversation and returns its id in the response; "
            "pass that value back on subsequent turns to keep context."
        ),
    )


class UsageInfo(BaseModel):
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None


class ChatResponse(BaseModel):
    reply: str
    model: str
    conversation_id: str
    usage: UsageInfo | None = None
    tool_calls: int = 0


class McpServerStatus(BaseModel):
    name: str
    url: str
    enabled: bool
    authenticated: bool


class McpStatusResponse(BaseModel):
    servers: list[McpServerStatus]


class HealthResponse(BaseModel):
    ok: bool = True
    version: str


class ConversationSummary(BaseModel):
    id: str
    title: str | None
    created_at: str
    updated_at: str
    message_count: int


class ConversationListResponse(BaseModel):
    conversations: list[ConversationSummary]


class StoredTurn(BaseModel):
    """One row of the messages table, rendered for API consumers.

    `role` and `text` are best-effort human-readable summaries extracted
    from the underlying ModelMessage parts; `parts` is the full serialized
    JSON so clients that want to replay tool calls can.
    """

    id: int
    ts: str
    role: Literal["user", "assistant", "system", "tool", "unknown"]
    text: str
    parts: list[dict[str, Any]]


class ConversationDetailResponse(BaseModel):
    id: str
    title: str | None
    created_at: str
    updated_at: str
    messages: list[StoredTurn]


class DeleteResponse(BaseModel):
    deleted: bool
