"""Message and stream vocabulary plus the model adapter seam.

Upstream: packages/llm/llm (``@deepseek-ai/dsh-llm``) at ce7073d.

Ported so far (Phase 2, needed by ``harness.core.session``): branded ids, the message
value types and their immutable constructors (``message.ts``), and call configuration
equality (``call-config.ts``). The adapter seam, stream assembly, errors and retry
policy follow in Phase 4.

Python differences:

- Messages, content blocks, tool schemas and configs are frozen JSON mappings
  (:class:`harness.util.values.FrozenJsonObject`); the type names below are documented
  aliases for those mappings, not separate classes. Field names keep upstream's
  camelCase because they are the persisted and model-visible JSON.
- Branded ids are :class:`typing.NewType` over ``str``; branding has no runtime effect,
  exactly as upstream.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from typing import Any, NewType

from harness.util.values import snapshot_json_value

__all__ = [
    "AssistantMessage",
    "ContentBlock",
    "DeveloperMessage",
    "LlmCallConfig",
    "LlmCallConfigAdapterDefaults",
    "LlmFailure",
    "Message",
    "MessageId",
    "ReasoningEffortId",
    "SystemMessage",
    "TokenUsage",
    "ToolCallId",
    "ToolHistory",
    "ToolResultMessage",
    "ToolSchema",
    "UserMessage",
    "call_config_equals",
    "create_assistant_message",
    "create_developer_message",
    "create_message",
    "create_system_message",
    "create_tool_result_message",
    "create_user_message",
    "freeze_message",
]

MessageId = NewType("MessageId", str)
"""Stable identity carried by one message across inbox, log and model-request boundaries."""

ToolCallId = NewType("ToolCallId", str)
"""Correlates a model-issued tool call with its result."""

ProviderRequestId = NewType("ProviderRequestId", str)
"""Provider-issued request identifier retained for diagnostics."""

LlmAttemptId = NewType("LlmAttemptId", str)
"""Identity of one model streaming attempt, unique within one Agent lifecycle."""

ReasoningEffortId = NewType("ReasoningEffortId", str)
"""Adapter-owned identifier for one model's selectable reasoning effort."""

ContentBlock = Mapping[str, Any]
"""One model-facing block, discriminated by ``type``: ``text``, ``reasoning``, ``image``,
``file``, ``tool-call``, ``tool-addition`` or ``tool-removal``."""

Message = Mapping[str, Any]
"""A persisted conversation message: ``id``, ``role``, ``content`` (blocks) and ``source``."""

SystemMessage = Message
"""``role: "system"`` with ``source: {"kind": "system-prompt"}``; empty content sends no prompt."""

DeveloperMessage = Message
"""``role: "developer"``: incremental session changes such as tool additions and removals."""

UserMessage = Message
"""``role: "user"``, with any producer's ``source``."""

AssistantMessage = Message
"""``role: "assistant"`` with ``source: {"kind": "model", "provider", "model", "replayState"?}``."""

ToolResultMessage = Message
"""``role: "tool"`` with ``source: {"kind": "tool", "callId"}``, ``toolCallId`` and ``isError``?."""

ToolSchema = Mapping[str, Any]
"""``name``, ``description``, ``parameters`` (a JSON Schema object) and ``deferLoading``?."""

ToolHistory = Mapping[str, Any]
"""``tools`` (active declarations) and ``updates`` (``messageId`` plus resolved ``additions``)."""

LlmCallConfig = Mapping[str, Any]
"""``provider`` and ``model``, plus ``reasoningEffort``, ``temperature``, ``maxTokens``
and ``stop``."""

LlmCallConfigAdapterDefaults = Mapping[str, Any]
"""``reasoningEffort: true`` and/or ``maxTokens: true`` when the adapter supplied them."""

TokenUsage = Mapping[str, Any]
"""``inputTokens``, ``outputTokens`` and optional total, cache and reasoning counts."""

LlmFailure = Mapping[str, Any]
"""``message`` and ``code``, plus ``status``, ``providerRetryAfterMs``, ``requestId``,
``offloadImages`` when available."""


def call_config_equals(a: LlmCallConfig, b: LlmCallConfig) -> bool:
    """Field-wise equality over call configurations, including the ``stop`` list."""
    for field in ("provider", "model", "reasoningEffort", "temperature", "maxTokens"):
        if a.get(field) != b.get(field):
            return False
    stop_a, stop_b = a.get("stop"), b.get("stop")
    if stop_a is None or stop_b is None:
        return stop_a is stop_b
    return len(stop_a) == len(stop_b) and all(x == y for x, y in zip(stop_a, stop_b, strict=True))


def _new_id() -> MessageId:
    return MessageId(str(uuid.uuid4()))


def _frozen_copy(message: Mapping[str, Any]) -> Message:
    snapshot = snapshot_json_value(message, freeze=True)
    if snapshot is None:
        raise ValueError("message is not lossless JSON")
    return snapshot


def freeze_message(message: Message) -> Message:
    """Detach and deep-freeze a message whose identity already exists."""
    return _frozen_copy(message)


def create_message(**fields: Any) -> Message:
    """Create one identified, immutable message from its role, content and source."""
    if "id" in fields:
        raise TypeError("create_message assigns the id; pass an existing message to freeze_message")
    return _frozen_copy({**fields, "id": _new_id()})


def create_developer_message(
    *, content: Sequence[ContentBlock], source: Mapping[str, Any], **rest: Any
) -> Message:
    """Create an identified, immutable developer message."""
    return create_message(**rest, content=content, source=source, role="developer")


def create_user_message(
    *, content: Sequence[ContentBlock], source: Mapping[str, Any], **rest: Any
) -> Message:
    """Create one identified, immutable user-role message."""
    return create_message(**rest, content=content, source=source, role="user")


def create_assistant_message(
    *, content: Sequence[ContentBlock], source: Mapping[str, Any]
) -> Message:
    """Create one identified, immutable model-produced assistant message.

    ``source`` carries ``provider``, ``model`` and optional ``replayState``; the
    ``kind: "model"`` tag is added here.
    """
    return create_message(role="assistant", content=content, source={"kind": "model", **source})


def create_system_message(text: str) -> Message:
    """Create one identified, immutable system message; ``""`` records "no system prompt"."""
    return create_message(
        role="system",
        content=[] if not text else [{"type": "text", "text": text}],
        source={"kind": "system-prompt"},
    )


def create_tool_result_message(
    *, call_id: ToolCallId | str, content: Sequence[ContentBlock], is_error: bool
) -> Message:
    """Create one identified, immutable tool-result message answering ``call_id``."""
    return create_message(
        role="tool",
        source={"kind": "tool", "callId": call_id},
        toolCallId=call_id,
        content=content,
        isError=is_error,
    )
