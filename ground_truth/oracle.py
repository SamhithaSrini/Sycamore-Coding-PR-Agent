"""
Oracle — aggregates all ground truth signals into a scalar reward.

CRITICAL: This module is NEVER imported by agents/ or core/.
Only to_reward_signal() leaves this layer — agents never see raw test output,
judge scores, or coverage numbers.
"""

from dataclasses import dataclass
import os

REWARD_WEIGHTS = {
    "tests": 0.50,
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
        }


def compute_oracle_reward(
    test_result: dict,
    judge_result: dict,
    preference_score: float,
) -> OracleResult:
    test_score = test_result.get("pass_rate", 0.0)
    judge_score = judge_result.get("overall_score", 0.0)
    test_error = test_result.get("error")

    # Invalid patches and reward hacking are never usable training examples, even
    # if the judge misses the pathology or the uncertainty score looks low.
    invalid_patch_errors = {"empty_diff", "patch_timeout"}
    invalid_patch = (
        test_error in invalid_patch_errors
        or str(test_error or "").startswith("patch_failed")
    )
    if invalid_patch or judge_result.get("reward_hacking_detected"):
        return OracleResult(
            test_pass_rate=test_score,
            test_coverage_delta=test_result.get("coverage_delta", 0.0),
            tests_added=test_result.get("tests_added", 0),
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
        + REWARD_WEIGHTS["judge"] * judge_score
        + REWARD_WEIGHTS["preference"] * preference_score
    )

    # Uncertainty = population std dev across active signal sources.
    signals = [test_score, judge_score, preference_score]
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
        judge_score=judge_score,
        judge_confidence=judge_result.get("confidence", 0.0),
        judge_dimensions=judge_result.get("dimensions", {}),
        reward_hacking_detected=False,
        preference_score=preference_score,
        final_reward=final_reward,
        reward_uncertainty=reward_uncertainty,
        use_for_training=use_for_training,
    )
