from __future__ import annotations

import json
import logging
import os
from abc import ABC, abstractmethod
from pathlib import Path

from pydantic import ValidationError

from colayout.llm.mock_layouts import load_mock_layout
from colayout.llm.placement_messages import (
    build_placement_user_message,
    parse_llm_json,
)
from colayout.llm.validate_placement import validate_layout_draft
from colayout.schemas.floor import RoomSpec
from colayout.schemas.layout_draft import RoomLayoutDraft

__all__ = [
    "LLMProvider",
    "MockLLMProvider",
    "OpenAILLMProvider",
    "build_placement_user_message",
    "get_llm_provider",
]

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[3]
PLACEMENT_PROMPT_PATH = ROOT / "config" / "prompts" / "room_placement.txt"
MAX_ATTEMPTS = 2


class LLMProvider(ABC):
    @abstractmethod
    def generate_layout_draft(
        self,
        room: RoomSpec,
        *,
        exclude_golden_ids: frozenset[str] | None = None,
    ) -> RoomLayoutDraft:
        raise NotImplementedError


class MockLLMProvider(LLMProvider):
    """Deterministic catalog kit for tests and offline runs."""

    def generate_layout_draft(
        self,
        room: RoomSpec,
        *,
        exclude_golden_ids: frozenset[str] | None = None,
    ) -> RoomLayoutDraft:
        data = load_mock_layout(room)
        data["room_id"] = room.id
        data["room_type"] = room.type
        draft = RoomLayoutDraft.model_validate(data)
        sanitized, _ = validate_layout_draft(draft, room)
        return sanitized


class OpenAILLMProvider(LLMProvider):
    def __init__(self, model: str | None = None) -> None:
        from openai import OpenAI

        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if not api_key:
            raise ValueError("OPENAI_API_KEY is not set")
        self._client = OpenAI(api_key=api_key)
        self._model = model or os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        self._placement_system = PLACEMENT_PROMPT_PATH.read_text(encoding="utf-8")
        self.last_generation_warnings: list[str] = []

    def generate_layout_draft(
        self,
        room: RoomSpec,
        *,
        exclude_golden_ids: frozenset[str] | None = None,
    ) -> RoomLayoutDraft:
        self.last_generation_warnings = []
        last_errors: list[str] = []

        for attempt in range(MAX_ATTEMPTS):
            try:
                resp = self._client.chat.completions.create(
                    model=self._model,
                    messages=self._build_placement_messages(
                        room, last_errors, exclude_golden_ids=exclude_golden_ids
                    ),
                    temperature=0.2,
                    response_format={"type": "json_object"},
                )
            except Exception as e:
                last_errors = [str(e)]
                logger.warning(
                    "Room %s placement attempt %d API error: %s",
                    room.id,
                    attempt + 1,
                    e,
                )
                continue

            raw = resp.choices[0].message.content or "{}"
            try:
                data = parse_llm_json(raw)
                data["room_id"] = room.id
                data["room_type"] = room.type
                draft = RoomLayoutDraft.model_validate(data)
                if not draft.placements:
                    last_errors = ["placements list is empty"]
                    continue
                sanitized, val_msgs = validate_layout_draft(draft, room)
                self.last_generation_warnings.extend(val_msgs)
                if not sanitized.placements:
                    last_errors = ["placements list is empty after sanitization"]
                    continue
                if val_msgs:
                    logger.info(
                        "Room %s placement sanitization: %s",
                        room.id,
                        "; ".join(val_msgs),
                    )
                return sanitized
            except (json.JSONDecodeError, ValidationError) as e:
                last_errors = [str(e)]
                logger.warning(
                    "Room %s placement attempt %d parse error: %s",
                    room.id,
                    attempt + 1,
                    e,
                )

        logger.warning(
            "Room %s: placement LLM failed after %d attempts; mock fallback. "
            "Last errors: %s",
            room.id,
            MAX_ATTEMPTS,
            "; ".join(last_errors) if last_errors else "none",
        )
        self.last_generation_warnings.append(
            "(warning) LLM placement failed; using deterministic mock layout"
        )
        return _placement_fallback(room)

    def _build_placement_messages(
        self,
        room: RoomSpec,
        errors: list[str],
        *,
        exclude_golden_ids: frozenset[str] | None = None,
    ) -> list[dict]:
        user_content = build_placement_user_message(
            room, exclude_golden_ids=exclude_golden_ids
        )
        messages: list[dict] = [
            {"role": "system", "content": self._placement_system},
            {"role": "user", "content": user_content},
        ]
        if errors:
            messages.append(
                {
                    "role": "user",
                    "content": (
                        "Previous response was invalid. Issues:\n"
                        + "\n".join(f"- {e}" for e in errors)
                        + "\nReturn corrected JSON only."
                    ),
                }
            )
        return messages


def _placement_fallback(room: RoomSpec) -> RoomLayoutDraft:
    data = load_mock_layout(room)
    data["room_id"] = room.id
    data["room_type"] = room.type
    draft = RoomLayoutDraft.model_validate(data)
    sanitized, errors = validate_layout_draft(draft, room)
    if errors:
        logger.warning("Placement fallback warnings for %s: %s", room.id, errors)
    return sanitized


def get_llm_provider(use_mock: bool = False) -> LLMProvider:
    if use_mock:
        return MockLLMProvider()
    if os.getenv("OPENAI_API_KEY", "").strip():
        return OpenAILLMProvider()
    logger.info("No OPENAI_API_KEY; using MockLLMProvider")
    return MockLLMProvider()
