"""Tests for signal extractor and alignment-aware routing."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from learning.signal_extractor import extract_training_signals


def _make_trace(
    reward=0.8,
    use_for_training=True,
    alignment=0.9,
    alignment_interp="high",
    test_pass=0.9,
    approved=True,
    reward_hacking=False,
    diff="--- a/src/click/core.py\n+++ b/src/click/core.py\n@@ -1 +1 @@\n-old\n+new\n--- a/tests/test_core.py\n+++ b/tests/test_core.py\n@@ -1 +1 @@\n-old\n+new",
    persona_reviews=None,
):
    persona_reviews = persona_reviews if persona_reviews is not None else {}
    return {
        "trace_id": "test-trace",
        "issue_body": "Fix the bug",
        "issue_title": "Test issue",
        "final_decision": "approved" if approved else "max_rounds_reached",
        "total_rounds": 2 if alignment else 1,
        "final_pr": {"diff": diff, "description": "Fix"},
        "pr_attempts": [
            {"attempt_number": 1, "diff": "old diff", "description": "", "timestamp": "", "coder_self_critique": "", "linter_passed": True, "static_analysis_issues": []},
            {"attempt_number": 2, "diff": "new diff", "description": "", "timestamp": "", "coder_self_critique": "", "linter_passed": True, "static_analysis_issues": []},
        ],
        "review_attempts": [
            {
                "attempt_number": 1,
                "decision": "request_changes",
                "comments": [{"content": "fix x", "severity": "blocking", "category": "correctness", "persona": "correctness", "confidence": 0.9}],
                "reviewer_confidence": 0.8,
                "persona_consensus": 1.0,
                "timestamp": "",
                "alignment_score": alignment,
                "persona_reviews": persona_reviews,
            }
        ],
        "confidence": {
            "final_reward": reward,
            "use_for_training": use_for_training,
            "reviewer_coder_alignment": alignment,
            "alignment_interpretation": alignment_interp,
            "test_pass_rate": test_pass,
            "judge_score": reward,
            "judge_reasoning": "good",
            "reward_hacking_detected": reward_hacking,
        },
    }


def test_high_alignment_high_reward_is_positive_for_both():
    trace = _make_trace(reward=0.85, alignment=0.9, test_pass=0.95)
    signals = extract_training_signals([trace])
    assert len(signals["coder_positive"]) == 1
    assert len(signals["reviewer_positive"]) == 1
    assert len(signals["coder_negative"]) == 0


def test_low_alignment_high_reward_is_reviewer_negative():
    trace = _make_trace(reward=0.85, alignment=0.2, alignment_interp="low", test_pass=0.95)
    signals = extract_training_signals([trace])
    assert len(signals["reviewer_negative"]) >= 1
    reason = signals["reviewer_negative"][0].get("reason", "")
    assert "low_alignment" in reason


def test_low_alignment_low_reward_is_coder_negative():
    trace = _make_trace(reward=0.25, alignment=0.2, alignment_interp="low", test_pass=0.3, approved=False)
    signals = extract_training_signals([trace])
    assert len(signals["coder_negative"]) >= 1
    assert signals["coder_negative"][0]["reason"] == "ignored_reviewer_feedback"


def test_reward_hacking_goes_to_negative():
    trace = _make_trace(reward=0.9, alignment=None, reward_hacking=True, diff="")
    # Reward hacking → use_for_training=False → alignment routing skipped
    trace["confidence"]["use_for_training"] = False
    signals = extract_training_signals([trace])
    # Should not appear in positive (use_for_training=False)
    assert all(ex.get("reward", 0) < 0.9 or ex.get("source") != "high_alignment_gt_good"
               for ex in signals["coder_positive"])
    assert signals["coder_negative"][0]["reason"] == "empty_diff"


def test_test_only_patch_is_coder_negative():
    diff = "--- a/tests/test_core.py\n+++ b/tests/test_core.py\n@@ -1 +1 @@\n-old\n+new"
    trace = _make_trace(reward=0.1, alignment=None, test_pass=0.9, approved=False, diff=diff)
    signals = extract_training_signals([trace])
    assert signals["coder_negative"][0]["reason"] == "test_only_patch"
    assert signals["coder_negative"][0]["review_feedback"]
    assert signals["coder_negative"][0]["judge_reasoning"] == "good"


def test_reviewer_learns_from_rejecting_bad_pr():
    trace = _make_trace(reward=0.1, alignment=None, test_pass=0.2, approved=False)
    trace["confidence"]["use_for_training"] = False
    signals = extract_training_signals([trace])
    assert len(signals["reviewer_positive"]) == 1


def test_debate_signal_records_right_and_wrong_personas():
    trace = _make_trace(
        reward=0.9,
        alignment=0.9,
        test_pass=0.95,
        persona_reviews={
            "correctness": {"decision": "approve"},
            "security": {"decision": "request_changes"},
        },
    )
    signals = extract_training_signals([trace])
    assert signals["debate_signals"][0]["correct_personas"] == ["correctness"]
    assert signals["debate_signals"][0]["wrong_personas"] == ["security"]


def test_stats_are_computed():
    traces = [
        _make_trace(reward=0.9, alignment=0.9, alignment_interp="high"),
        _make_trace(reward=0.2, alignment=0.15, alignment_interp="low", test_pass=0.2, approved=False),
    ]
    signals = extract_training_signals(traces)
    assert signals["stats"]["total_traces"] == 2
    assert signals["stats"]["high_alignment_traces"] >= 1
    assert signals["stats"]["low_alignment_traces"] >= 1
