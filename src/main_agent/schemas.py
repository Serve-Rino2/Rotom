"""Request / response Pydantic models exposed by the HTTP API."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, description="The new user message")
    history: list[ChatMessage] | None = Field(
        default=None,
        description="Prior turns. Currently advisory — the agent is stateless per request.",
    )


class UsageInfo(BaseModel):
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None


class ChatResponse(BaseModel):
    reply: str
    model: str
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
