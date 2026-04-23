"""Load the MCP server registry from YAML and build Pydantic AI toolsets."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import yaml
from pydantic_ai.mcp import MCPServerSSE, MCPServerStreamableHTTP


_ENV_PATTERN = re.compile(r"\$\{([A-Z0-9_]+)\}")

Transport = Literal["streamable_http", "sse"]

McpToolset = MCPServerStreamableHTTP | MCPServerSSE


def _expand_env(value: object) -> object:
    """Replace ${VAR} tokens in strings with their env value.

    Unset or empty vars collapse to an empty string so ``token: ${FOO}``
    naturally turns into no-auth when FOO isn't set. Non-strings pass
    through untouched.
    """
    if not isinstance(value, str):
        return value
    return _ENV_PATTERN.sub(lambda m: os.environ.get(m.group(1), ""), value)


@dataclass(frozen=True)
class McpServerSpec:
    name: str
    url: str
    token: str | None
    enabled: bool
    transport: Transport = "streamable_http"

    def to_toolset(self) -> McpToolset:
        headers = {"Authorization": f"Bearer {self.token}"} if self.token else None
        if self.transport == "sse":
            return MCPServerSSE(url=self.url, headers=headers)
        return MCPServerStreamableHTTP(url=self.url, headers=headers)


def load_registry(path: Path) -> list[McpServerSpec]:
    with path.open("r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}

    servers_raw = raw.get("servers") or []
    specs: list[McpServerSpec] = []
    for entry in servers_raw:
        name = str(entry["name"]).strip()
        url = str(_expand_env(entry["url"])).strip()
        token_raw = _expand_env(entry.get("token"))
        token = token_raw.strip() if isinstance(token_raw, str) and token_raw.strip() else None
        enabled = bool(entry.get("enabled", True))
        transport = str(entry.get("transport", "streamable_http")).strip().lower()
        if transport not in ("streamable_http", "sse"):
            raise ValueError(
                f"MCP server '{name}' has unsupported transport '{transport}' "
                f"(expected 'streamable_http' or 'sse')"
            )

        if not url:
            raise ValueError(f"MCP server '{name}' has an empty URL after env expansion")

        specs.append(
            McpServerSpec(
                name=name,
                url=url,
                token=token,
                enabled=enabled,
                transport=transport,  # type: ignore[arg-type]
            )
        )

    return specs


def build_toolsets(specs: list[McpServerSpec]) -> list[McpToolset]:
    return [spec.to_toolset() for spec in specs if spec.enabled]
