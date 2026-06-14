#!/usr/bin/env python3
"""Cache LLM-only designs for preference training (offline)."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from colayout.preference.llm_designs import (  # noqa: E402
    LLM_DESIGNS_DIR,
    cache_random_designs,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Cache LLM layout drafts for preference training."
    )
    parser.add_argument(
        "--per-type",
        type=int,
        default=3,
        help="Designs per room type (default: 3)",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Use MockLLMProvider instead of OpenAI",
    )
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Regenerate even when cache file exists",
    )
    args = parser.parse_args()

    saved = cache_random_designs(
        per_type=args.per_type,
        use_mock=args.mock,
        seed=args.seed,
        overwrite=args.overwrite,
    )
    logger.info("Cached %d designs under %s", len(saved), LLM_DESIGNS_DIR)
    for rec in saved:
        n = len((rec.get("draft") or {}).get("placements") or [])
        logger.info(
            "  %s — %s %.1f×%.1f m (%d pieces)",
            rec["design_id"],
            rec["room_type"],
            rec["width_m"],
            rec["length_m"],
            n,
        )


if __name__ == "__main__":
    main()
