"""Tests for confidence bundle and oracle reward computation."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from ground_truth.oracle import compute_oracle_reward, OracleResult


def _make_inputs(test_pass=0.9, lean_verified=True, judge_score=0.85, pref=0.75, hack=False):
    return (
        {"pass_rate": test_pass, "coverage_delta": 0.02, "tests_added": 2},
        {"verified": lean_verified, "coverage": 0.8, "passed": 4, "total": 5},
        {"overall_score": judge_score, "confidence": 0.9, "dimensions": {},
         "reward_hacking_detected": hack, "reasoning": "test", "lean_propositions": []},
        pref,
    )


def test_high_quality_pr():
    result = compute_oracle_reward(*_make_inputs())
    assert result.final_reward > 0.8
    assert result.use_for_training is True
    assert result.reward_hacking_detected is False


def test_reward_hacking_zeroes_reward():
    result = compute_oracle_reward(*_make_inputs(hack=True))
    assert result.final_reward == 0.0
    assert result.use_for_training is False
    assert result.reward_hacking_detected is True


def test_high_uncertainty_blocks_training():
    # Extreme disagreement between signals
    result = compute_oracle_reward(*_make_inputs(test_pass=1.0, lean_verified=False, judge_score=0.1))
    assert result.reward_uncertainty >= 0.25 or result.use_for_training is False


def test_reward_signal_hides_raw_gt():
    result = compute_oracle_reward(*_make_inputs())
    signal = result.to_reward_signal()
    assert "test_pass_rate" not in signal
    assert "final_reward" in signal
    assert signal["test_signal"] in ("pass", "fail", "partial")
    assert signal["lean_signal"] in ("verified", "unverified", "not_applicable")


def test_lean_not_applicable():
    result = compute_oracle_reward(*_make_inputs(lean_verified=None))
    assert result.lean_verified is None
    assert result.to_reward_signal()["lean_signal"] == "not_applicable"
