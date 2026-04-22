"""Pydantic AI Agent wired to GLM (OpenAI-compatible) and MCP toolsets."""

from __future__ import annotations

from pydantic_ai import Agent
from pydantic_ai.mcp import MCPServerStreamableHTTP
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from .config import Settings


def build_agent(
    settings: Settings, toolsets: list[MCPServerStreamableHTTP]
) -> Agent:
    provider = OpenAIProvider(
        base_url=settings.glm_base_url,
        api_key=settings.glm_api_key,
    )
    model = OpenAIChatModel(settings.glm_model, provider=provider)

    return Agent(
        model=model,
        system_prompt=settings.system_prompt,
        toolsets=list(toolsets),
    )
