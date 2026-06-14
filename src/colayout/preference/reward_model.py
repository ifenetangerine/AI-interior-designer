"""Logistic preference reward model R(features) — Phase B."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from colayout.preference.features import FEATURE_NAMES, features_vector


def _sigmoid(x: float) -> float:
    if x >= 0:
        z = math.exp(-x)
        return 1.0 / (1.0 + z)
    z = math.exp(x)
    return z / (1.0 + z)


@dataclass
class RewardModel:
    """Linear model: score = w·features + bias."""

    weights: list[float] = field(default_factory=lambda: [0.0] * len(FEATURE_NAMES))
    bias: float = 0.0
    trained: bool = False

    def score(self, features: dict[str, float]) -> float:
        vec = features_vector(features)
        total = self.bias
        for w, v in zip(self.weights, vec):
            total += w * v
        return total

    def prob_a_beats_b(
        self,
        features_a: dict[str, float],
        features_b: dict[str, float],
    ) -> float:
        return _sigmoid(self.score(features_a) - self.score(features_b))

    def fit(
        self,
        comparisons: list[dict],
        *,
        epochs: int = 200,
        lr: float = 0.05,
    ) -> None:
        """Fit on logged comparisons with winner A or B (skip ties)."""
        pairs = [
            c
            for c in comparisons
            if c.get("winner") in ("A", "B")
            and c.get("features_A")
            and c.get("features_B")
        ]
        if len(pairs) < 5:
            return

        n_feat = len(FEATURE_NAMES)
        w = [0.0] * n_feat
        b = 0.0

        for _ in range(epochs):
            for row in pairs:
                fa = features_vector(row["features_A"])
                fb = features_vector(row["features_B"])
                label = 1.0 if row["winner"] == "A" else 0.0
                diff = [a - bb for a, bb in zip(fa, fb)]
                logit = b + sum(wi * di for wi, di in zip(w, diff))
                pred = _sigmoid(logit)
                err = pred - label
                b -= lr * err
                for i in range(n_feat):
                    w[i] -= lr * err * diff[i]

        self.weights = w
        self.bias = b
        self.trained = True
