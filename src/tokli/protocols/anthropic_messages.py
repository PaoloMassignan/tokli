"""Anthropic Messages adapter (SPEC 003): request ⇄ canonical segments, patch-based rendering.

Only string values are exposed as segments (mapping table in SPEC 003). Every other part is
opaque and is re-emitted unchanged. With no effective patch the original bytes are returned
(CM-001); otherwise the patched strings are written at their locators and the body is serialised
once as compact UTF-8 JSON (CM-002, CM-011).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from tokli.domain.models import (
    MUTABLE_ELIGIBLE,
    CanonicalRequest,
    Patch,
    Segment,
    SegmentKind,
    ToolRecord,
)

PROTOCOL = "anthropic_messages"
PROVIDER = "anthropic"
ENDPOINT = "/v1/messages"


class ParseError(Exception):
    """The body is not a Messages request this adapter can map (CM-007)."""


class _Builder:
    def __init__(self, mutable_kinds: frozenset[SegmentKind]) -> None:
        self.segments: list[Segment] = []
        self._mutable = mutable_kinds & MUTABLE_ELIGIBLE

    def add(
        self,
        kind: SegmentKind,
        text: object,
        locator: str,
        role: str | None,
        *,
        block: dict[str, Any] | None = None,
        tool_name: str | None = None,
        tool_call_id: str | None = None,
        is_error: bool = False,
        whole_result: bool = False,
    ) -> None:
        if not isinstance(text, str):
            return
        index = len(self.segments)
        self.segments.append(
            Segment(
                id=f"s{index}",
                index=index,
                kind=kind,
                role=role,
                text=text,
                locator=locator,
                mutable=kind in self._mutable,
                tool_name=tool_name,
                tool_call_id=tool_call_id,
                is_error=is_error,
                whole_result=whole_result,
                cache_breakpoint_after=bool(block is not None and "cache_control" in block),
            )
        )


def _text_blocks(
    builder: _Builder,
    blocks: list[Any],
    base: str,
    kind: SegmentKind,
    role: str | None,
    **attrs: Any,
) -> None:
    for j, block in enumerate(blocks):
        if isinstance(block, dict) and block.get("type") == "text":
            builder.add(kind, block.get("text"), f"{base}/{j}/text", role, block=block, **attrs)


def conversation_key(request: CanonicalRequest) -> str:
    """SHA-256 of the canonical JSON of `system` and the first message (ADR 0012): the same for
    every request of one conversation, different for another conversation."""
    body = request.original_json if isinstance(request.original_json, dict) else {}
    messages = body.get("messages")
    first = messages[0] if isinstance(messages, list) and messages else None
    canonical = json.dumps(
        {"system": body.get("system"), "first": first},
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _pointer_part(key: str) -> str:
    return key.replace("~", "~0").replace("/", "~1")


def _argument_strings(node: Any, parts: list[str], pointer: str) -> list[tuple[str, str]]:
    """``(pointer, value)`` for each string at a field path such as ``edits/*/old_string``."""
    if not parts:
        return [(pointer, node)] if isinstance(node, str) else []
    head, rest = parts[0], parts[1:]
    if head == "*":
        if not isinstance(node, list):
            return []
        found: list[tuple[str, str]] = []
        for index, item in enumerate(node):
            found += _argument_strings(item, rest, f"{pointer}/{index}")
        return found
    if not isinstance(node, dict) or head not in node:
        return []
    return _argument_strings(node[head], rest, f"{pointer}/{_pointer_part(head)}")


def _is_human_turn(message: dict[str, Any]) -> bool:
    """A user message holding human text; tool-only messages and messages that mix tool
    results with text are not human turns (SPEC 019 PR-026)."""
    if message.get("role") != "user":
        return False
    content = message.get("content")
    if isinstance(content, str):
        return True
    if not isinstance(content, list):
        return False
    types = {block.get("type") for block in content if isinstance(block, dict)}
    return "text" in types and "tool_result" not in types


def parse(
    raw: bytes,
    *,
    mutable_kinds: frozenset[SegmentKind],
    arg_fields: Mapping[str, Sequence[str]] | None = None,
) -> CanonicalRequest:
    try:
        body = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ParseError(f"not JSON: {exc}") from exc
    if not isinstance(body, dict):
        raise ParseError("body is not a JSON object")
    messages = body.get("messages")
    if not isinstance(messages, list) or not all(isinstance(m, dict) for m in messages):
        raise ParseError("'messages' is not a list of objects")

    builder = _Builder(mutable_kinds)

    system = body.get("system")
    if isinstance(system, str):
        builder.add(SegmentKind.SYSTEM, system, "/system", "system")
    elif isinstance(system, list):
        _text_blocks(builder, system, "/system", SegmentKind.SYSTEM, "system")

    tools = body.get("tools")
    if isinstance(tools, list):
        for k, tool in enumerate(tools):
            if isinstance(tool, dict):
                builder.add(
                    SegmentKind.TOOL_DESCRIPTION,
                    tool.get("description"),
                    f"/tools/{k}/description",
                    None,
                )

    tool_names: dict[str, str] = {}
    calls: list[tuple[str, str, Any, int]] = []
    human_turns: list[int] = []
    for i, message in enumerate(messages):
        role = message.get("role")
        content = message.get("content")
        base = f"/messages/{i}/content"
        if _is_human_turn(message):
            human_turns.append(i)
        if role == "user":
            if isinstance(content, str):
                builder.add(SegmentKind.USER_TEXT, content, base, "user")
            elif isinstance(content, list):
                for j, block in enumerate(content):
                    if not isinstance(block, dict):
                        continue
                    kind = block.get("type")
                    if kind == "text":
                        builder.add(
                            SegmentKind.USER_TEXT,
                            block.get("text"),
                            f"{base}/{j}/text",
                            "user",
                            block=block,
                        )
                    elif kind == "tool_result":
                        call_id = (
                            block.get("tool_use_id")
                            if isinstance(block.get("tool_use_id"), str)
                            else None
                        )
                        attrs: dict[str, Any] = {
                            "tool_name": tool_names.get(call_id) if call_id else None,
                            "tool_call_id": call_id,
                            "is_error": block.get("is_error") is True,
                        }
                        inner = block.get("content")
                        if isinstance(inner, str):
                            builder.add(
                                SegmentKind.TOOL_RESULT,
                                inner,
                                f"{base}/{j}/content",
                                "user",
                                block=block,
                                whole_result=True,
                                **attrs,
                            )
                        elif (
                            isinstance(inner, list)
                            and len(inner) == 1
                            and isinstance(inner[0], dict)
                            and inner[0].get("type") == "text"
                        ):
                            builder.add(
                                SegmentKind.TOOL_RESULT,
                                inner[0].get("text"),
                                f"{base}/{j}/content/0/text",
                                "user",
                                block=inner[0],  # its own cache_control, as for any text block
                                whole_result=True,
                                **attrs,
                            )
                        elif isinstance(inner, list):
                            _text_blocks(
                                builder,
                                inner,
                                f"{base}/{j}/content",
                                SegmentKind.TOOL_RESULT,
                                "user",
                                **attrs,
                            )
        elif role == "assistant" and isinstance(content, list):
            for j, block in enumerate(content):
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "text":
                    builder.add(
                        SegmentKind.ASSISTANT_TEXT,
                        block.get("text"),
                        f"{base}/{j}/text",
                        "assistant",
                        block=block,
                    )
                elif (
                    block.get("type") == "tool_use"
                    and isinstance(block.get("id"), str)
                    and isinstance(block.get("name"), str)
                ):
                    tool_names[block["id"]] = block["name"]
                    calls.append((block["id"], block["name"], block.get("input"), i))
                    for path in (arg_fields or {}).get(block["name"], ()):
                        found = _argument_strings(
                            block.get("input"), path.split("/"), f"{base}/{j}/input"
                        )
                        for pointer, value in found:
                            builder.add(
                                SegmentKind.TOOL_CALL_ARGS,
                                value,
                                pointer,
                                "assistant",
                                tool_name=block["name"],
                                tool_call_id=block["id"],
                            )
        elif role == "assistant" and isinstance(content, str):
            builder.add(SegmentKind.ASSISTANT_TEXT, content, base, "assistant")

    results: dict[str, list[str]] = {}
    for segment in builder.segments:
        if segment.tool_call_id is not None and segment.kind is SegmentKind.TOOL_RESULT:
            results.setdefault(segment.tool_call_id, []).append(segment.id)
    tools = tuple(
        ToolRecord(
            call_id,
            name,
            arguments,
            index,
            tuple(results.get(call_id, ())),
            human_turns_after=sum(1 for turn in human_turns if turn > message_index),
        )
        for index, (call_id, name, arguments, message_index) in enumerate(calls)
    )
    model = body.get("model")
    return CanonicalRequest(
        protocol=PROTOCOL,
        provider=PROVIDER,
        endpoint=ENDPOINT,
        model=model if isinstance(model, str) else None,
        stream=body.get("stream") is True,
        segments=tuple(builder.segments),
        original_json=body,
        original_bytes=raw,
        tools=tools,
    )


def _set(document: Any, pointer: str, value: str) -> None:
    parts = [p.replace("~1", "/").replace("~0", "~") for p in pointer.split("/")[1:]]
    node = document
    for part in parts[:-1]:
        node = node[int(part)] if isinstance(node, list) else node[part]
    last = parts[-1]
    if isinstance(node, list):
        node[int(last)] = value
    else:
        node[last] = value


def render(request: CanonicalRequest, patches: Sequence[Patch]) -> bytes:
    effective = [p for p in patches if p.new_text != request.segment(p.segment_id).text]
    if not effective:
        return request.original_bytes
    document = json.loads(request.original_bytes)
    for patch in effective:
        _set(document, request.segment(patch.segment_id).locator, patch.new_text)
    return json.dumps(document, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


# Binary payloads that the provider does not count as text (TM-004): block type → field.
_BINARY_FIELDS = {"thinking": "signature", "redacted_thinking": "data"}
_MEDIA_BLOCKS = frozenset({"image", "document"})


def _skeleton(node: Any, pointer: str, segment_pointers: frozenset[str]) -> Any:
    """A copy of ``node`` with segment texts and binary payloads replaced by empty strings."""
    if isinstance(node, dict):
        kind = node.get("type")
        out: dict[str, Any] = {}
        for key, value in node.items():
            child = f"{pointer}/{key.replace('~', '~0').replace('/', '~1')}"
            if isinstance(value, str) and (
                child in segment_pointers or _BINARY_FIELDS.get(str(kind)) == key
            ):
                out[key] = ""
            elif key == "source" and kind in _MEDIA_BLOCKS and isinstance(value, dict):
                out[key] = {k: "" if k == "data" else v for k, v in value.items()}
            else:
                out[key] = _skeleton(value, child, segment_pointers)
        return out
    if isinstance(node, list):
        return [
            ""
            if isinstance(v, str) and f"{pointer}/{i}" in segment_pointers
            else _skeleton(v, f"{pointer}/{i}", segment_pointers)
            for i, v in enumerate(node)
        ]
    return node


def estimate_request_tokens(request: CanonicalRequest, count: Callable[[str], int]) -> int:
    """Local estimate of the whole request as sent (TM-004, TOKLI_TELEMETRY_AND_COST §1).

    Every segment text is counted on its own, plus the JSON of the remaining structure without
    binary payloads. The structure is counted per top-level key and per message, so with a
    caching ``count`` the unchanged history of a conversation costs almost nothing.
    """
    body = request.original_json
    if not isinstance(body, dict):
        return 0
    pointers = frozenset(s.locator for s in request.segments)
    total = sum(count(s.text) for s in request.segments)
    for key, value in body.items():
        pointer = f"/{key.replace('~', '~0').replace('/', '~1')}"
        if key == "messages" and isinstance(value, list):
            parts = [
                _skeleton(message, f"{pointer}/{i}", pointers) for i, message in enumerate(value)
            ]
        else:
            parts = [{key: _skeleton(value, pointer, pointers)}]
        for part in parts:
            total += count(json.dumps(part, ensure_ascii=False, separators=(",", ":")))
    return total
