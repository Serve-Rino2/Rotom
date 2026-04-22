"""Conversation store — CRUD + Pydantic AI message (de)serialization.

Conversation history lives in SQLite so a client can carry a
`conversation_id` across /chat calls and the agent will replay the
prior turns as Pydantic AI `message_history`. Messages are stored
one row per `ModelMessage`, serialized via the SDK's adapter so
tool-call context (arguments, returns) is preserved faithfully.
"""

from __future__ import annotations

import sqlite3
import uuid
from dataclasses import dataclass
from typing import Any

from pydantic_ai.messages import ModelMessage, ModelMessagesTypeAdapter


@dataclass(frozen=True)
class ConversationSummary:
    id: str
    title: str | None
    created_at: str
    updated_at: str
    message_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "message_count": self.message_count,
        }


@dataclass(frozen=True)
class StoredMessage:
    id: int
    conv_id: str
    ts: str
    data: str

    def decode(self) -> ModelMessage:
        msgs = ModelMessagesTypeAdapter.validate_json(self.data)
        # stored as a one-element array to keep the wire format symmetric
        # with the SDK's `new_messages_json()`.
        return msgs[0]


def create_conversation(
    conn: sqlite3.Connection,
    *,
    conv_id: str | None = None,
    title: str | None = None,
) -> str:
    """Create a new conversation row. Returns its id (generated if not given)."""
    cid = conv_id or str(uuid.uuid4())
    conn.execute(
        "INSERT INTO conversations (id, title) VALUES (?, ?)",
        (cid, title),
    )
    conn.commit()
    return cid


def touch(conn: sqlite3.Connection, conv_id: str) -> None:
    conn.execute(
        "UPDATE conversations SET updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (conv_id,),
    )
    conn.commit()


def exists(conn: sqlite3.Connection, conv_id: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM conversations WHERE id = ?",
        (conv_id,),
    ).fetchone()
    return row is not None


def load_history(conn: sqlite3.Connection, conv_id: str) -> list[ModelMessage]:
    """Return the message_history to pass into `agent.run(..., message_history=...)`."""
    rows = conn.execute(
        "SELECT data FROM messages WHERE conv_id = ? ORDER BY id ASC",
        (conv_id,),
    ).fetchall()
    out: list[ModelMessage] = []
    for row in rows:
        msgs = ModelMessagesTypeAdapter.validate_json(row["data"])
        out.extend(msgs)
    return out


def append_messages(
    conn: sqlite3.Connection,
    *,
    conv_id: str,
    new_messages_json: bytes,
) -> None:
    """Persist `result.new_messages_json()` splitting into one row per message.

    We validate first to know how many messages we're storing, then write
    each as its own single-element JSON array so the decode path is
    symmetric (every row round-trips through ModelMessagesTypeAdapter).
    """
    msgs = ModelMessagesTypeAdapter.validate_json(new_messages_json)
    for m in msgs:
        single = ModelMessagesTypeAdapter.dump_json([m]).decode("utf-8")
        conn.execute(
            "INSERT INTO messages (conv_id, data) VALUES (?, ?)",
            (conv_id, single),
        )
    conn.execute(
        "UPDATE conversations SET updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (conv_id,),
    )
    conn.commit()


def get_conversation_summary(
    conn: sqlite3.Connection,
    conv_id: str,
) -> ConversationSummary | None:
    row = conn.execute(
        """
        SELECT c.id, c.title, c.created_at, c.updated_at,
               (SELECT COUNT(*) FROM messages m WHERE m.conv_id = c.id) AS n
        FROM conversations c
        WHERE c.id = ?
        """,
        (conv_id,),
    ).fetchone()
    if row is None:
        return None
    return ConversationSummary(
        id=row["id"],
        title=row["title"],
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
        message_count=int(row["n"]),
    )


def list_conversations(
    conn: sqlite3.Connection,
    *,
    limit: int = 50,
    offset: int = 0,
) -> list[ConversationSummary]:
    rows = conn.execute(
        """
        SELECT c.id, c.title, c.created_at, c.updated_at,
               (SELECT COUNT(*) FROM messages m WHERE m.conv_id = c.id) AS n
        FROM conversations c
        ORDER BY c.updated_at DESC
        LIMIT ? OFFSET ?
        """,
        (limit, offset),
    ).fetchall()
    return [
        ConversationSummary(
            id=r["id"],
            title=r["title"],
            created_at=str(r["created_at"]),
            updated_at=str(r["updated_at"]),
            message_count=int(r["n"]),
        )
        for r in rows
    ]


def get_messages(
    conn: sqlite3.Connection,
    *,
    conv_id: str,
) -> list[StoredMessage]:
    rows = conn.execute(
        "SELECT id, conv_id, ts, data FROM messages WHERE conv_id = ? ORDER BY id ASC",
        (conv_id,),
    ).fetchall()
    return [
        StoredMessage(
            id=int(r["id"]),
            conv_id=r["conv_id"],
            ts=str(r["ts"]),
            data=r["data"],
        )
        for r in rows
    ]


def delete_conversation(conn: sqlite3.Connection, conv_id: str) -> bool:
    cur = conn.execute("DELETE FROM conversations WHERE id = ?", (conv_id,))
    conn.commit()
    return cur.rowcount > 0


def set_title_if_missing(
    conn: sqlite3.Connection,
    *,
    conv_id: str,
    title: str,
) -> None:
    """Populate `title` on first append if it was left null at creation.

    Trimmed to 80 characters so a runaway first message doesn't wreck
    the conversation list UI.
    """
    trimmed = title.strip()[:80]
    if not trimmed:
        return
    conn.execute(
        """
        UPDATE conversations
        SET title = ?
        WHERE id = ? AND (title IS NULL OR title = '')
        """,
        (trimmed, conv_id),
    )
    conn.commit()
