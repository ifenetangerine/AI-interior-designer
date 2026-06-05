from __future__ import annotations

import json
import logging
import os
import re
from abc import ABC, abstractmethod
from pathlib import Path

from pydantic import ValidationError

from colayout.catalog.kenney_index import catalog_prompt_json
from colayout.llm.mock_kits import load_mock_kit
from colayout.llm.mock_layouts import load_mock_layout
from colayout.llm.room_program import (
    anchor_category,
    density_tier,
    furniture_count_bounds,
    placement_wall_guidance,
    principles_excerpt,
    room_area_m2,
)
from colayout.llm.validate import validate_and_sanitize
from colayout.llm.validate_placement import (
    is_blocking_placement_error,
    is_retry_pressure_error,
    validate_layout_draft,
)
from colayout.schemas.floor import RoomSpec
from colayout.schemas.layout_draft import RoomLayoutDraft
from colayout.schemas.scene import RoomSceneGraph

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[3]
PROMPT_PATH = ROOT / "config" / "prompts" / "room_furniture.txt"
PLACEMENT_PROMPT_PATH = ROOT / "config" / "prompts" / "room_placement.txt"
MAX_ATTEMPTS = 3


class LLMProvider(ABC):
    @abstractmethod
    def generate_layout_draft(self, room: RoomSpec) -> RoomLayoutDraft:
        raise NotImplementedError

    def generate_scene_graph(self, room: RoomSpec) -> RoomSceneGraph:
        """Legacy IP-full path."""
        raise NotImplementedError


class MockLLMProvider(LLMProvider):
    """Deterministic catalog kit for tests and offline runs."""

    def generate_layout_draft(self, room: RoomSpec) -> RoomLayoutDraft:
        data = load_mock_layout(room)
        data["room_id"] = room.id
        data["room_type"] = room.type
        draft = RoomLayoutDraft.model_validate(data)
        sanitized, _ = validate_layout_draft(draft, room)
        return sanitized

    def generate_scene_graph(self, room: RoomSpec) -> RoomSceneGraph:
        data = load_mock_kit(room)
        data["room_id"] = room.id
        data["room_type"] = room.type
        graph = RoomSceneGraph.model_validate(data)
        sanitized, _ = validate_and_sanitize(graph, room)
        return sanitized


class OpenAILLMProvider(LLMProvider):
    def __init__(self, model: str | None = None, use_baseline: bool = False) -> None:
        from openai import OpenAI

        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if not api_key:
            raise ValueError("OPENAI_API_KEY is not set")
        self._client = OpenAI(api_key=api_key)
        self._model = model or os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        self._system = PROMPT_PATH.read_text(encoding="utf-8")
        self._placement_system = PLACEMENT_PROMPT_PATH.read_text(encoding="utf-8")
        self._use_baseline = use_baseline
        self.last_generation_warnings: list[str] = []

    def generate_layout_draft(self, room: RoomSpec) -> RoomLayoutDraft:
        self.last_generation_warnings = []
        last_errors: list[str] = []

        for attempt in range(MAX_ATTEMPTS):
            messages = self._build_placement_messages(room, last_errors)
            try:
                resp = self._client.chat.completions.create(
                    model=self._model,
                    messages=messages,
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
                data = _parse_json(raw)
                data["room_id"] = room.id
                data["room_type"] = room.type
                draft = RoomLayoutDraft.model_validate(data)
                sanitized, val_errors = validate_layout_draft(draft, room)
                blocking = [
                    e for e in val_errors if is_blocking_placement_error(e)
                ]
                retry_pressure = [
                    e for e in val_errors if is_retry_pressure_error(e)
                ]
                if blocking:
                    last_errors = val_errors
                    logger.warning(
                        "Room %s placement attempt %d: %s",
                        room.id,
                        attempt + 1,
                        "; ".join(blocking),
                    )
                    continue
                if retry_pressure and attempt < MAX_ATTEMPTS - 1:
                    last_errors = val_errors
                    logger.info(
                        "Room %s placement attempt %d retry pressure: %s",
                        room.id,
                        attempt + 1,
                        "; ".join(retry_pressure),
                    )
                    continue
                if val_errors:
                    logger.info(
                        "Room %s placement warnings: %s",
                        room.id,
                        "; ".join(val_errors),
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

    def generate_scene_graph(self, room: RoomSpec) -> RoomSceneGraph:
        last_errors: list[str] = []

        for attempt in range(MAX_ATTEMPTS):
            messages = self._build_messages(room, last_errors)
            try:
                resp = self._client.chat.completions.create(
                    model=self._model,
                    messages=messages,
                    temperature=0.2,
                    response_format={"type": "json_object"},
                )
            except Exception as e:
                last_errors = [str(e)]
                logger.warning(
                    "Room %s scene graph attempt %d API error: %s",
                    room.id,
                    attempt + 1,
                    e,
                )
                continue
            raw = resp.choices[0].message.content or "{}"
            try:
                data = _parse_json(raw)
                data["room_id"] = room.id
                data["room_type"] = room.type
                graph = RoomSceneGraph.model_validate(data)
                sanitized, val_errors = validate_and_sanitize(graph, room)
                blocking = [e for e in val_errors if _is_blocking_error(e)]
                if blocking:
                    last_errors = val_errors
                    logger.warning(
                        "Room %s attempt %d validation: %s",
                        room.id,
                        attempt + 1,
                        "; ".join(blocking),
                    )
                    continue
                if val_errors:
                    logger.info(
                        "Room %s sanitized with warnings: %s",
                        room.id,
                        "; ".join(val_errors),
                    )
                return sanitized
            except (json.JSONDecodeError, ValidationError) as e:
                last_errors = [str(e)]
                logger.warning(
                    "Room %s attempt %d parse error: %s", room.id, attempt + 1, e
                )

        logger.warning(
            "Room %s: LLM design failed after %d attempts; using template fallback. "
            "Last errors: %s",
            room.id,
            MAX_ATTEMPTS,
            "; ".join(last_errors) if last_errors else "none",
        )
        return _template_fallback(room)

    def _build_placement_messages(
        self,
        room: RoomSpec,
        errors: list[str],
    ) -> list[dict]:
        user_content = build_placement_user_message(room)
        messages: list[dict] = [
            {"role": "system", "content": self._placement_system},
            {"role": "user", "content": user_content},
        ]
        if errors:
            messages.append(
                {
                    "role": "user",
                    "content": (
                        "Fix the layout draft. Issues:\n"
                        + "\n".join(f"- {e}" for e in errors)
                        + "\nReturn corrected JSON only."
                    ),
                }
            )
        return messages

    def _build_messages(
        self,
        room: RoomSpec,
        errors: list[str],
    ) -> list[dict]:
        user_content = build_user_message(room)
        messages: list[dict] = [
            {"role": "system", "content": self._system},
            {"role": "user", "content": user_content},
        ]
        if errors:
            messages.append(
                {
                    "role": "user",
                    "content": (
                        "Fix the scene graph. Issues:\n"
                        + "\n".join(f"- {e}" for e in errors)
                        + "\nReturn corrected JSON only."
                    ),
                }
            )
        return messages


def build_placement_user_message(room: RoomSpec) -> str:
    area = room_area_m2(room)
    tier = density_tier(area)
    min_p, max_p = furniture_count_bounds(room.type, tier)
    parts = [
        f"Room id: {room.id}",
        f"Room type: {room.type}",
        f"Width (m): {room.width_m}",
        f"Length (m): {room.length_m}",
        f"Floor area: {area:.1f} m²",
        f"Density tier: {tier}",
        f"Target furniture count: {min_p}–{max_p} pieces",
        f"Anchor role: {anchor_category(room.type)}",
        f"Preferences: {room.preferences or 'none'}",
        "---",
        placement_wall_guidance(room),
        "---",
    ]
    excerpt = principles_excerpt(room.type)
    if excerpt:
        parts.extend(["Design principles (excerpt):", excerpt, "---"])
    parts.extend(
        [
            "Kenney catalog for this room (pick model_id from this list only):",
            catalog_prompt_json(room.type),
            "---",
            "Place all furniture with explicit center_x_m, center_z_m, orientation.",
        ]
    )
    return "\n".join(parts)


def build_user_message(room: RoomSpec) -> str:
    area = room_area_m2(room)
    tier = density_tier(area)
    min_p, max_p = furniture_count_bounds(room.type, tier)
    parts = [
        f"Room id: {room.id}",
        f"Room type: {room.type}",
        f"Width (m): {room.width_m}",
        f"Length (m): {room.length_m}",
        f"Floor area: {area:.1f} m²",
        f"Density tier: {tier}",
        f"Target furniture count: {min_p}–{max_p} pieces",
        f"Anchor role: {anchor_category(room.type)}",
        f"Preferences: {room.preferences or 'none'}",
        "---",
    ]
    excerpt = principles_excerpt(room.type)
    if excerpt:
        parts.extend(["Design principles (excerpt):", excerpt, "---"])
    parts.extend(
        [
            "Kenney catalog for this room (pick model_id from this list only):",
            catalog_prompt_json(room.type),
            "---",
            "Design a complete scene graph using only catalog model_ids above.",
        ]
    )
    return "\n".join(parts)


def _is_blocking_error(msg: str) -> bool:
    lower = msg.lower()
    if "empty" in lower:
        return True
    if "exceeds" in lower and "floor" in lower:
        return True
    if "below minimum" in lower:
        return True
    if "orphan furniture" in lower:
        return True
    if "chair per desk" in lower or "one chair per desk" in lower:
        return True
    if "dining_table needs" in lower:
        return True
    if "unknown model_id" in lower:
        return True
    if "not allowed in" in lower:
        return True
    if "missing model_id" in lower:
        return True
    return False


def _placement_fallback(room: RoomSpec) -> RoomLayoutDraft:
    data = load_mock_layout(room)
    data["room_id"] = room.id
    data["room_type"] = room.type
    draft = RoomLayoutDraft.model_validate(data)
    sanitized, errors = validate_layout_draft(draft, room)
    if errors:
        logger.warning("Placement fallback warnings for %s: %s", room.id, errors)
    return sanitized


def _template_fallback(room: RoomSpec) -> RoomSceneGraph:
    data = load_mock_kit(room)
    data["room_id"] = room.id
    data["room_type"] = room.type
    graph = RoomSceneGraph.model_validate(data)
    sanitized, errors = validate_and_sanitize(graph, room)
    if errors:
        logger.warning("Template fallback warnings for %s: %s", room.id, errors)
    return sanitized


def get_llm_provider(use_mock: bool = False) -> LLMProvider:
    if use_mock:
        return MockLLMProvider()
    if os.getenv("OPENAI_API_KEY", "").strip():
        return OpenAILLMProvider()
    logger.info("No OPENAI_API_KEY; using MockLLMProvider")
    return MockLLMProvider()


def _parse_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return json.loads(text)
