"""Preference trainer: Phase A nudge, Phase B reward model."""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any

from colayout.preference.reward_model import RewardModel
from colayout.preference.store import (
    append_comparison,
    get_room_theta_state,
    load_comparisons,
    set_room_theta_state,
)
from colayout.preference.theta import (
    clamp_theta,
    default_theta,
    explore_theta,
    nudge_theta,
    sample_theta_pair,
    schema_payload_grouped,
    theta_schema,
)

PHASE_A_LIMIT = 100
NUDGE_ALPHA = 0.15


@dataclass
class TrainerState:
    room_type: str
    theta_current: dict[str, float]
    comparison_count: int
    phase: str

    @property
    def phase_label(self) -> str:
        return "A" if self.comparison_count < PHASE_A_LIMIT else "B"


class PreferenceTrainer:
    def __init__(self, room_type: str) -> None:
        self.room_type = room_type
        self._reward = RewardModel()

    def load_state(self) -> TrainerState:
        raw = get_room_theta_state(self.room_type)
        theta = clamp_theta(raw.get("theta_current", {}), self.room_type)
        count = int(raw.get("comparison_count", 0))
        return TrainerState(
            room_type=self.room_type,
            theta_current=theta,
            comparison_count=count,
            phase="A" if count < PHASE_A_LIMIT else "B",
        )

    def _save_state(self, state: TrainerState) -> None:
        set_room_theta_state(
            self.room_type,
            {
                "theta_current": state.theta_current,
                "comparison_count": state.comparison_count,
            },
        )

    def sample_pair(
        self,
        rng: random.Random | None = None,
    ) -> tuple[dict[str, float], dict[str, float]]:
        state = self.load_state()
        comparisons = load_comparisons(self.room_type)

        if state.comparison_count >= PHASE_A_LIMIT:
            self._reward.fit(comparisons)
            if self._reward.trained:
                return self._sample_pair_phase_b(state.theta_current, rng)

        block_index = state.comparison_count % 3
        return sample_theta_pair(
            state.theta_current,
            self.room_type,
            rng=rng,
            block_index=block_index,
        )

    def _sample_pair_phase_b(
        self,
        theta_current: dict[str, float],
        rng: random.Random | None,
    ) -> tuple[dict[str, float], dict[str, float]]:
        rng = rng or random.Random()
        comparisons = load_comparisons(self.room_type)
        block_index = len(comparisons) % 3
        return sample_theta_pair(
            theta_current,
            self.room_type,
            rng=rng,
            block_index=block_index,
        )

    def record_comparison(
        self,
        *,
        design_id: str,
        theta_a: dict[str, float],
        theta_b: dict[str, float],
        winner: str,
        features_a: dict[str, float],
        features_b: dict[str, float],
    ) -> TrainerState:
        state = self.load_state()
        phase = state.phase_label

        if winner == "tie":
            state.comparison_count += 1
            state.theta_current = explore_theta(
                state.theta_current, self.room_type, rng=random.Random()
            )
            state.phase = "A" if state.comparison_count < PHASE_A_LIMIT else "B"
            self._save_state(state)
            append_comparison(
                {
                    "room_type": self.room_type,
                    "design_id": design_id,
                    "theta_A": theta_a,
                    "theta_B": theta_b,
                    "winner": "tie",
                    "features_A": features_a,
                    "features_B": features_b,
                    "comparison_index": state.comparison_count - 1,
                    "phase": phase,
                }
            )
            return state

        if winner == "A":
            theta_winner, theta_loser = theta_a, theta_b
        elif winner == "B":
            theta_winner, theta_loser = theta_b, theta_a
        else:
            raise ValueError(f"Invalid winner: {winner}")

        if state.comparison_count < PHASE_A_LIMIT:
            new_theta = nudge_theta(
                state.theta_current,
                theta_winner,
                theta_loser,
                self.room_type,
                alpha=NUDGE_ALPHA,
            )
        else:
            comparisons = load_comparisons(self.room_type)
            comparisons.append(
                {
                    "winner": winner,
                    "features_A": features_a,
                    "features_B": features_b,
                }
            )
            self._reward.fit(comparisons)
            new_theta = clamp_theta(theta_winner, self.room_type)

        state.comparison_count += 1
        state.theta_current = new_theta
        state.phase = "A" if state.comparison_count < PHASE_A_LIMIT else "B"
        self._save_state(state)

        append_comparison(
            {
                "room_type": self.room_type,
                "design_id": design_id,
                "theta_A": theta_a,
                "theta_B": theta_b,
                "winner": winner,
                "features_A": features_a,
                "features_B": features_b,
                "comparison_index": state.comparison_count - 1,
                "phase": phase,
            }
        )
        return state

    def top_theta_deltas(self, n: int = 5) -> list[dict[str, Any]]:
        state = self.load_state()
        defaults = default_theta(self.room_type)
        deltas: list[tuple[str, float]] = []
        for key, val in state.theta_current.items():
            deltas.append((key, val - defaults.get(key, val)))
        deltas.sort(key=lambda x: abs(x[1]), reverse=True)
        return [{"key": k, "delta": d} for k, d in deltas[:n]]

    def schema_payload(self) -> list[dict[str, Any]]:
        return schema_payload_grouped(self.room_type)
