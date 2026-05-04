"""
Oracle — aggregates all ground truth signals into a scalar reward.

CRITICAL: This module is NEVER imported by agents/ or core/.
Only to_reward_signal() leaves this layer — agents never see raw test output,
Lean proofs, or coverage numbers.
"""

from dataclasses import dataclass
from typing import Optional
import os

REWARD_WEIGHTS = {
    "tests": 0.50,
    "lean": 0.00,   # Lean4 binary not installed — weight redistributed to tests/judge
    "judge": 0.35,
    "preference": 0.15,
}

UNCERTAINTY_THRESHOLD = float(os.getenv("REWARD_UNCERTAINTY_THRESHOLD", "0.25"))


@dataclass
class OracleResult:
    # Raw signals (never exposed to agents)
    test_pass_rate: float
    test_coverage_delta: float
    tests_added: int
    lean_verified: Optional[bool]
    lean_coverage: float
    lean_passed: int
    lean_total: int
    judge_score: float
    judge_confidence: float
    judge_dimensions: dict
    reward_hacking_detected: bool
    preference_score: float

    # Composite
    final_reward: float
    reward_uncertainty: float           # std dev across signals
    use_for_training: bool

    def to_reward_signal(self) -> dict:
        """
        The ONLY interface between ground truth and agents/learning layers.
        Directional hints only — no raw numbers.
        """
        return {
            "final_reward": self.final_reward,
            "reward_uncertainty": self.reward_uncertainty,
            "use_for_training": self.use_for_training,
            "reward_hacking_detected": self.reward_hacking_detected,
            "test_signal": (
                "pass" if self.test_pass_rate > 0.9 else
                "fail" if self.test_pass_rate < 0.5 else
                "partial"
            ),
            "lean_signal": (
                "verified" if self.lean_verified is True else
                "unverified" if self.lean_verified is False else
                "not_applicable"
            ),
        }


def compute_oracle_reward(
    test_result: dict,
    lean_result: dict,
    judge_result: dict,
    preference_score: float,
) -> OracleResult:
    test_score = test_result.get("pass_rate", 0.0)
    lean_verified = lean_result.get("verified")
    lean_score = 1.0 if lean_verified is True else 0.0 if lean_verified is False else 0.5

    judge_score = judge_result.get("overall_score", 0.0)

    # Reward hacking detected → zero reward, not usable for training
    if judge_result.get("reward_hacking_detected"):
        return OracleResult(
            test_pass_rate=test_score,
            test_coverage_delta=test_result.get("coverage_delta", 0.0),
            tests_added=test_result.get("tests_added", 0),
            lean_verified=lean_verified,
            lean_coverage=lean_result.get("coverage", 0.0),
            lean_passed=lean_result.get("passed", 0),
            lean_total=lean_result.get("total", 0),
            judge_score=judge_score,
            judge_confidence=judge_result.get("confidence", 0.0),
            judge_dimensions=judge_result.get("dimensions", {}),
            reward_hacking_detected=True,
            preference_score=preference_score,
            final_reward=0.0,
            reward_uncertainty=1.0,
            use_for_training=False,
        )

    final_reward = (
        REWARD_WEIGHTS["tests"] * test_score
        + REWARD_WEIGHTS["lean"] * lean_score
        + REWARD_WEIGHTS["judge"] * judge_score
        + REWARD_WEIGHTS["preference"] * preference_score
    )

    # Uncertainty = population std dev across active signal sources (lean excluded when binary absent)
    active_signals = [test_score, judge_score, preference_score]
    if REWARD_WEIGHTS["lean"] > 0:
        active_signals.append(lean_score)
    signals = active_signals
    mean = sum(signals) / len(signals)
    variance = sum((s - mean) ** 2 for s in signals) / len(signals)
    reward_uncertainty = variance ** 0.5

    use_for_training = (
        reward_uncertainty < UNCERTAINTY_THRESHOLD
        and not judge_result.get("reward_hacking_detected", False)
    )

    return OracleResult(
        test_pass_rate=test_score,
        test_coverage_delta=test_result.get("coverage_delta", 0.0),
        tests_added=test_result.get("tests_added", 0),
        lean_verified=lean_verified,
        lean_coverage=lean_result.get("coverage", 0.0),
        lean_passed=lean_result.get("passed", 0),
        lean_total=lean_result.get("total", 0),
        judge_score=judge_score,
        judge_confidence=judge_result.get("confidence", 0.0),
        judge_dimensions=judge_result.get("dimensions", {}),
        reward_hacking_detected=False,
        preference_score=preference_score,
        final_reward=final_reward,
        reward_uncertainty=reward_uncertainty,
        use_for_training=use_for_training,
    )
