"""Tests for confidence bundle and oracle reward computation."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from ground_truth.oracle import compute_oracle_reward, OracleResult
from core.coder_agent import _is_valid_coding_diff


def _make_inputs(test_pass=0.9, judge_score=0.85, pref=0.75, hack=False):
    return (
        {"pass_rate": test_pass, "coverage_delta": 0.02, "tests_added": 2},
        {"overall_score": judge_score, "confidence": 0.9, "dimensions": {},
         "reward_hacking_detected": hack, "reasoning": "test"},
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


def test_empty_diff_zeroes_reward_even_if_judge_misses_it():
    test_result, judge_result, pref = _make_inputs()
    test_result = {**test_result, "pass_rate": 0.0, "error": "empty_diff"}
    judge_result = {**judge_result, "reward_hacking_detected": False}
    result = compute_oracle_reward(test_result, judge_result, pref)
    assert result.final_reward == 0.0
    assert result.use_for_training is False
    assert result.reward_hacking_detected is True


def test_high_uncertainty_blocks_training():
    # Extreme disagreement between signals
    result = compute_oracle_reward(*_make_inputs(test_pass=1.0, judge_score=0.1))
    assert result.reward_uncertainty >= 0.25 or result.use_for_training is False


def test_reward_signal_hides_raw_gt():
    result = compute_oracle_reward(*_make_inputs())
    signal = result.to_reward_signal()
    assert "test_pass_rate" not in signal
    assert "final_reward" in signal
    assert signal["test_signal"] in ("pass", "fail", "partial")


def test_coder_diff_validation_requires_source_change():
    assert not _is_valid_coding_diff("")
    assert not _is_valid_coding_diff(
        "--- a/tests/test_core.py\n+++ b/tests/test_core.py\n@@ -1 +1 @@\n-old\n+new"
    )
    assert _is_valid_coding_diff(
        "--- a/src/click/core.py\n+++ b/src/click/core.py\n@@ -1 +1 @@\n-old\n+new"
    )


def test_coder_diff_validation_rejects_test_deletion_and_false_test_claims():
    source_and_test_delete = (
        "--- a/src/click/core.py\n+++ b/src/click/core.py\n@@ -1 +1 @@\n-old\n+new\n"
        "--- a/tests/test_core.py\n+++ b/tests/test_core.py\n@@ -1,2 +1,1 @@\n-old\n-assert x\n+old\n"
    )
    assert not _is_valid_coding_diff(source_and_test_delete)
    source_only = "--- a/src/click/core.py\n+++ b/src/click/core.py\n@@ -1 +1 @@\n-old\n+new"
    assert not _is_valid_coding_diff(source_only, "Tests: added regression test")
