"""
Signal Extractor

Extracts training signals from collected interaction traces.
Combines reward signals, alignment scores, and debate signals
into separate training sets for coder and reviewer fine-tuning.

Alignment-aware logic:
  high alignment + high reward  → positive for BOTH agents
  low alignment  + high reward  → reviewer gave irrelevant comments → reviewer negative
  low alignment  + low reward   → coder ignored valid feedback      → coder negative
  high alignment + low reward   → deeper issue → flag, don't train on this
"""

import json
from pathlib import Path
from typing import List


def extract_training_signals(traces: list) -> dict:
    """
    traces: list of dicts (from JSON) or InteractionTrace objects.
    Returns separate signal sets for coder and reviewer training.
    """
    coder_positive = []
    coder_negative = []
    reviewer_positive = []
    reviewer_negative = []
    debate_signals = []     # High-signal: MoE persona disagreements resolved by GT
    alignment_signals = []  # Alignment score breakdown per trace

    for trace in traces:
        t = trace if isinstance(trace, dict) else trace.to_dict()
        if t.get("is_held_out"):
            continue
        cb = t.get("confidence") or {}
        if not cb:
            continue

        final_reward = cb.get("final_reward", 0.0)
        use_for_training = cb.get("use_for_training", False)
        reward_hacking = cb.get("reward_hacking_detected", False)
        alignment = cb.get("reviewer_coder_alignment")  # None if single-round
        alignment_interp = cb.get("alignment_interpretation", "single_round")
        gt_good = cb.get("test_pass_rate", 0.0) > 0.8 and final_reward > 0.7
        reviewer_approved = t.get("final_decision") == "approved"
        final_pr = t.get("final_pr") or {}
        patch_stats = _patch_stats(final_pr.get("diff", ""))

        # ── Alignment-aware signal routing ──────────────────────────
        if alignment is not None and use_for_training:
            alignment_signals.append({
                "trace_id": t.get("trace_id"),
                "alignment": alignment,
                "interpretation": alignment_interp,
                "final_reward": final_reward,
                "gt_good": gt_good,
            })

            high_align = alignment >= 0.8
            low_align = alignment < 0.4

            if high_align and gt_good:
                # Both agents performing well
                coder_positive.append(_make_coder_example(t, final_pr, final_reward, "high_alignment_gt_good"))
                reviewer_positive.append(_make_reviewer_example(t, "gt_confirmed_high_alignment"))

            elif low_align and gt_good:
                # Reviewer gave irrelevant/unactionable comments; coder succeeded anyway
                reviewer_negative.append({
                    **_make_reviewer_example(t, "gt_good_but_low_alignment"),
                    "reason": "low_alignment_with_good_outcome: reviewer comments were not actionable",
                    "gt_assessment": "good",
                })

            elif low_align and not gt_good:
                # Coder ignored valid feedback
                coder_negative.append({
                    **_make_coder_example(t, final_pr, final_reward, "low_alignment_gt_bad"),
                    "reward": final_reward,
                    "reason": "ignored_reviewer_feedback",
                })

            elif high_align and not gt_good:
                # Coder addressed all feedback but code still bad — don't use for fine-tuning
                # This is a signal that reviewer feedback was itself wrong
                reviewer_negative.append({
                    **_make_reviewer_example(t, "high_alignment_but_bad_outcome"),
                    "reason": "reviewer_feedback_was_wrong: coder followed it but GT failed",
                    "gt_assessment": "bad",
                })

        else:
            # Single round or alignment not computed — use reward-only routing
            if use_for_training and final_reward > 0.75:
                coder_positive.append(_make_coder_example(t, final_pr, final_reward, "high_reward"))
            elif reward_hacking or final_reward < 0.3:
                coder_negative.append({
                    **_make_coder_example(t, final_pr, final_reward, "negative_outcome"),
                    "reward": final_reward,
                    "reason": _coder_failure_reason(reward_hacking, final_reward, patch_stats),
                })

            # Reviewer learns from grounded outcomes even when the coder output is not
            # trainable, because catching a bad/reward-hacked PR is a positive review signal.
            if reviewer_approved == gt_good:
                reviewer_positive.append(_make_reviewer_example(t, "gt_confirmed"))
            elif reviewer_approved != gt_good:
                reviewer_negative.append({
                    **_make_reviewer_example(t, "gt_disagreement"),
                    "reviewer_decision": "approved" if reviewer_approved else "request_changes",
                    "gt_assessment": "good" if gt_good else "bad",
                    "judge_reasoning": cb.get("judge_reasoning", "")[:300],
                })

        # ── Debate signals (MoE persona disagreements) ─────────────
        for i, review in enumerate(t.get("review_attempts", [])):
            persona_reviews = review.get("persona_reviews", {})
            if not persona_reviews:
                continue
            decisions = {p: r.get("decision") for p, r in persona_reviews.items()}
            if len(set(decisions.values())) > 1:
                pr_diff = ""
                if i < len(t.get("pr_attempts", [])):
                    pr_diff = t["pr_attempts"][i].get("diff", "")
                debate_signals.append({
                    "pr_diff": pr_diff,
                    "persona_decisions": decisions,
                    "gt_correct": gt_good,
                    "correct_decision": "approve" if gt_good else "request_changes",
                    "which_persona_was_right": _correct_persona(decisions, gt_good),
                    "correct_personas": _personas_matching(decisions, gt_good),
                    "wrong_personas": _personas_not_matching(decisions, gt_good),
                    "alignment_score": review.get("alignment_score"),
                })

    return {
        "coder_positive": coder_positive,
        "coder_negative": coder_negative,
        "reviewer_positive": reviewer_positive,
        "reviewer_negative": reviewer_negative,
        "debate_signals": debate_signals,
        "alignment_signals": alignment_signals,
        "stats": {
            "total_traces": len(traces),
            "usable_for_training": sum(
                1 for t in traces
                if (t if isinstance(t, dict) else t.to_dict()).get("confidence", {}).get("use_for_training")
            ),
            "reward_hacking_detected": sum(
                1 for t in traces
                if (t if isinstance(t, dict) else t.to_dict()).get("confidence", {}).get("reward_hacking_detected")
            ),
            "high_alignment_traces": sum(
                1 for s in alignment_signals if s["interpretation"] == "high"
            ),
            "low_alignment_traces": sum(
                1 for s in alignment_signals if s["interpretation"] == "low"
            ),
        },
    }


def _make_coder_example(trace: dict, final_pr: dict, reward: float, source: str) -> dict:
    stats = _patch_stats(final_pr.get("diff", ""))
    confidence = trace.get("confidence") or {}
    return {
        "issue": trace.get("issue_body", ""),
        "issue_title": trace.get("issue_title", ""),
        "diff": final_pr.get("diff", ""),
        "description": final_pr.get("description", ""),
        "reward": reward,
        "judge_score": confidence.get("judge_score", reward),
        "test_pass_rate": confidence.get("test_pass_rate"),
        "judge_reasoning": confidence.get("judge_reasoning", ""),
        "review_feedback": _summarize_review_feedback(trace),
        "rounds_needed": trace.get("total_rounds", 1),
        "source": source,
        **stats,
    }


def _summarize_review_feedback(trace: dict, max_comments: int = 4) -> list:
    comments = []
    for review in trace.get("review_attempts", []):
        for comment in review.get("comments", []):
            severity = comment.get("severity", "suggestion")
            content = " ".join(comment.get("content", "").split())
            if content:
                comments.append(f"{severity}: {content}")
            if len(comments) >= max_comments:
                return comments
    return comments


def _make_reviewer_example(trace: dict, source: str) -> dict:
    reviews = trace.get("review_attempts", [])
    last_review = reviews[-1] if reviews else {}
    return {
        "pr_diff": (trace.get("final_pr") or {}).get("diff", ""),
        "decision": last_review.get("decision", ""),
        "comments": last_review.get("comments", []),
        "gt_confirmed": source in ("gt_confirmed", "gt_confirmed_high_alignment", "high_alignment_gt_good"),
        "source": source,
        "persona_reviews": last_review.get("persona_reviews", {}),
    }


def _correct_persona(decisions: dict, gt_good: bool) -> str:
    correct = "approve" if gt_good else "request_changes"
    for persona, decision in decisions.items():
        if decision == correct:
            return persona
    return "none"


def _personas_matching(decisions: dict, gt_good: bool) -> list:
    correct = "approve" if gt_good else "request_changes"
    return [persona for persona, decision in decisions.items() if decision == correct]


def _personas_not_matching(decisions: dict, gt_good: bool) -> list:
    correct = "approve" if gt_good else "request_changes"
    return [persona for persona, decision in decisions.items() if decision != correct]


def _patch_stats(diff: str) -> dict:
    files = []
    for line in diff.splitlines():
        if line.startswith("+++ b/"):
            files.append(line.removeprefix("+++ b/"))
    source_files = [f for f in files if f.startswith("src/") and f.endswith(".py")]
    test_files = [f for f in files if f.startswith("tests/") and f.endswith(".py")]
    return {
        "changed_files": files,
        "source_files": source_files,
        "test_files": test_files,
        "has_source_changes": bool(source_files),
        "has_test_changes": bool(test_files),
        "is_test_only": bool(test_files) and not source_files,
        "is_empty_diff": not diff.strip(),
    }


def _coder_failure_reason(reward_hacking: bool, final_reward: float, patch_stats: dict) -> str:
    if patch_stats["is_empty_diff"]:
        return "empty_diff"
    if patch_stats["is_test_only"]:
        return "test_only_patch"
    if reward_hacking:
        return "reward_hacking"
    if not patch_stats["has_source_changes"]:
        return "no_source_change"
    if final_reward < 0.3:
        return "low_quality"
    return "negative_outcome"


def load_all_traces() -> list:
    traces = []
    traces_dir = Path("data/traces")
    if not traces_dir.exists():
        return traces
    active_issue_ids = _active_training_issue_ids()
    for path in traces_dir.glob("*.json"):
        try:
            data = json.loads(path.read_text())
            if data.get("is_held_out"):
                continue
            if active_issue_ids and str(data.get("issue_id", "")) not in active_issue_ids:
                continue
            traces.append(data)
        except Exception as e:
            print(f"  Warning: could not load trace {path}: {e}")
    return traces


def _active_training_issue_ids() -> set:
    issues_dir = Path("data/issues")
    if not issues_dir.exists():
        return set()
    ids = set()
    for path in issues_dir.glob("*.json"):
        try:
            issue = json.loads(path.read_text())
            ids.add(str(issue.get("id", "")))
        except Exception:
            continue
    return ids
