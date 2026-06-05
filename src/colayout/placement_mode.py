"""Placement pipeline mode: LLM refine (default) vs legacy IP-full."""

from __future__ import annotations

import os

MODES = frozenset({"llm_refine", "ip_full", "llm_only"})


def get_placement_mode() -> str:
    mode = os.getenv("PLACEMENT_MODE", "llm_refine").strip().lower()
    if mode not in MODES:
        return "llm_refine"
    return mode


def resolve_placement_mode(override: str | None = None) -> str:
    if override:
        mode = override.strip().lower()
        if mode in MODES:
            return mode
    return get_placement_mode()


def is_llm_refine_mode(override: str | None = None) -> bool:
    return resolve_placement_mode(override) == "llm_refine"


def is_llm_only_mode(override: str | None = None) -> bool:
    return resolve_placement_mode(override) == "llm_only"
