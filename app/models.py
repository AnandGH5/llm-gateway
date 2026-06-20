from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class Message(BaseModel):
    # extra="allow" keeps fields like `name`, `tool_calls`, etc. intact.
    model_config = ConfigDict(extra="allow")

    role: str
    content: Any = None


class ChatCompletionRequest(BaseModel):
    """Minimal validation of the OpenAI chat schema.

    ``extra="allow"`` means any field we don't explicitly name (tools,
    response_format, top_p, ...) is preserved and forwarded untouched, which
    is what makes this a *transparent* proxy.
    """

    model_config = ConfigDict(extra="allow")

    model: str
    messages: list[Message]
    stream: bool = False
    temperature: float | None = None
    max_tokens: int | None = None
