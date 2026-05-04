"""
Interaction Loop

Orchestrates the full coder → reviewer → revise cycle for a single issue.
Computes the Reviewer–Coder Alignment Score between each round pair.

Flow:
  1. Coder generates PR (injecting reviewer patterns from recent traces)
  2. Pre-review hooks (linter, static analysis)
  3. Reviewer evaluates (MoE personas, injecting coder patterns from recent traces)
  4. [If approved or max rounds] → ground truth evaluation
  5. Alignment score computed for each round pair
  6. Oracle aggregates all signals → scalar reward
  7. Confidence bundle built and saved to trace
"""

import os
from datetime import datetime
from pathlib import Path

from core.coder_agent import generate_pr
from core.reviewer_agent import review_pr
from core.judge_agent import judge_pr
from core.confidence import build_confidence_bundle
from ground_truth.oracle import compute_oracle_reward
from ground_truth.test_runner import run_tests
from hooks.post_pr import run_pre_review_checks
from hooks.drift_detector import check_reviewer_drift, record_reviewer_gt_disagreement
from learning.trace_collector import (
    InteractionTrace, PRAttempt, ReviewAttempt, ReviewComment
)
from learning.alignment import compute_alignment
from learning.rlhf_pipeline import score_preference

MAX_ROUNDS = int(os.getenv("MAX_ROUNDS", "4"))


def run_interaction(
    issue: dict,
    training_cycle: int = 0,
    save_training_trace: bool = True,
) -> InteractionTrace:
    """
    Full interaction loop for a single issue.
    Returns a complete InteractionTrace with confidence bundle.
    """
    trace = InteractionTrace(
        issue_id=issue.get("id", ""),
        issue_title=issue.get("title", ""),
        issue_body=issue.get("body", ""),
        issue_labels=issue.get("labels", []),
        repo=os.getenv("GITHUB_REPO", os.getenv("PROJECT_NAME", "pallets/click")),
        training_cycle=training_cycle,
        coder_model_version=os.getenv("CODER_MODEL", "claude-haiku-4-5-20251001"),
        reviewer_model_version=os.getenv("REVIEWER_MODEL", "claude-haiku-4-5-20251001"),
    )

    current_diff = None
    last_review = None
    round_alignment_scores = []   # Alignment score per revision round

    for round_num in range(1, MAX_ROUNDS + 1):
        print(f"\n  Round {round_num}/{MAX_ROUNDS}: '{issue.get('title', '')[:60]}'")

        # ── Step 1: Coder generates / revises PR ─────────────────
        pr_result = generate_pr(
            issue=issue,
            review_feedback=_format_feedback(last_review) if last_review else None,
            previous_diff=current_diff,
        )

        if not pr_result.get("diff"):
            print(f"  Warning: coder returned empty diff on round {round_num}")

        # ── Step 2: Pre-review checks ─────────────────────────────
        pre_checks = run_pre_review_checks(pr_result.get("diff", ""))

        pr_attempt = PRAttempt(
            attempt_number=round_num,
            diff=pr_result.get("diff", ""),
            description=pr_result.get("description", ""),
            timestamp=datetime.utcnow().isoformat(),
            coder_self_critique=pr_result.get("self_critique", ""),
            linter_passed=pre_checks["linter_passed"],
            static_analysis_issues=[i["message"] for i in pre_checks["issues"]],
        )
        trace.pr_attempts.append(pr_attempt)

        # ── Step 2b: Alignment for previous review vs this diff ──
        # (computed AFTER new diff is available, BEFORE new review)
        if last_review and current_diff != pr_result.get("diff"):
            prev_review = trace.review_attempts[-1]
            comments = prev_review.comments
            alignment_result = compute_alignment(comments, pr_result.get("diff", ""))
            prev_review.alignment_score = alignment_result.get("score")
            prev_review.alignment_detail = {
                "interpretation": alignment_result.get("interpretation"),
                "addressed_count": len(alignment_result.get("addressed", [])),
                "not_addressed_count": len(alignment_result.get("not_addressed", [])),
                "training_signal": alignment_result.get("training_signal"),
            }
            round_alignment_scores.append(alignment_result.get("score"))
            if alignment_result.get("score") is not None:
                print(f"  Alignment score (round {round_num-1}→{round_num}): "
                      f"{alignment_result['score']:.2f} [{alignment_result.get('interpretation', '?')}]")

        current_diff = pr_result.get("diff", "")

        # ── Step 3: Reviewer evaluates ────────────────────────────
        review_result = review_pr(
            pr={
                "diff": pr_result.get("diff", ""),
                "description": pr_result.get("description", ""),
                "linter_passed": pre_checks["linter_passed"],
                "static_analysis_issues": pre_checks["issues"],
            },
            issue=issue,
        )

        # Convert comment dicts to ReviewComment dataclasses
        review_comments = [
            ReviewComment(
                content=c.get("content", ""),
                severity=c.get("severity", "suggestion"),
                category=c.get("category", "correctness"),
                persona=c.get("persona", ""),
                line=c.get("line"),
                file=c.get("file"),
                confidence=c.get("confidence", 0.8),
            )
            for c in review_result.get("comments", [])
        ]

        review_attempt = ReviewAttempt(
            attempt_number=round_num,
            decision=review_result["decision"],
            comments=review_comments,
            reviewer_confidence=review_result.get("reviewer_confidence", 0.5),
            persona_consensus=review_result.get("persona_consensus", 1.0),
            timestamp=datetime.utcnow().isoformat(),
            self_critique=review_result.get("self_critique", ""),
            persona_reviews=review_result.get("persona_reviews", {}),
        )
        trace.review_attempts.append(review_attempt)
        last_review = review_result

        # ── Drift detection ───────────────────────────────────────
        check_reviewer_drift(trace)

        # ── Step 4: Check terminal condition ─────────────────────
        approved = review_result["decision"] == "approve"
        is_final = approved or round_num == MAX_ROUNDS

        if is_final:
            decision_str = "approved" if approved else "max_rounds_reached"
            trace.final_pr = pr_attempt
            trace.final_decision = decision_str
            trace.total_rounds = round_num

            # ── Step 5: Ground truth evaluation ──────────────────
            print(f"\n  Ground truth evaluation (isolated)...")

            test_result = run_tests(pr_result.get("diff", ""))
            print(f"    Tests: pass_rate={test_result['pass_rate']:.2f}, "
                  f"coverage_delta={test_result.get('coverage_delta', 0):.3f}, "
                  f"tests_added={test_result.get('tests_added', 0)}")

            judge_result = judge_pr(
                pr={"diff": pr_result.get("diff", ""), "description": pr_result.get("description", "")},
                issue=issue,
                reviewer_decision=review_result["decision"],
                reviewer_comments=review_result.get("comments", []),
            )
            print(f"    Judge: {judge_result.get('overall_score', 0):.2f} "
                  f"(confidence: {judge_result.get('confidence', 0):.2f})")

            preference_score = score_preference(pr_result.get("diff", ""), issue)

            oracle = compute_oracle_reward(test_result, judge_result, preference_score)
            print(f"    Oracle: reward={oracle.final_reward:.3f}, "
                  f"uncertainty={oracle.reward_uncertainty:.3f}, "
                  f"use_for_training={oracle.use_for_training}")

            # Track reviewer accuracy for drift detection
            gt_good = oracle.test_pass_rate > 0.8 and oracle.final_reward > 0.7
            record_reviewer_gt_disagreement(approved, gt_good)

            # ── Step 6: Confidence bundle ─────────────────────────
            trace.confidence = build_confidence_bundle(
                oracle=oracle,
                judge_result=judge_result,
                reviewer_result=review_result,
                test_result=test_result,
                preference_score=preference_score,
                round_alignment_scores=round_alignment_scores,
            )

            # ── Step 7: Save trace ────────────────────────────────
            if save_training_trace:
                trace_path = Path("data/traces") / f"{trace.trace_id}.json"
                trace_path.parent.mkdir(parents=True, exist_ok=True)
                trace.save(str(trace_path))
                print(f"  Trace saved: {trace_path.name}")

            return trace

    return trace


def _format_feedback(review: dict) -> str:
    """Format MoE review into clear feedback for the coder."""
    blocking = [c for c in review.get("comments", []) if c.get("severity") == "blocking"]
    suggestions = [c for c in review.get("comments", []) if c.get("severity") == "suggestion"]

    parts = []
    if blocking:
        parts.append("BLOCKING ISSUES (must fix before approval):")
        for c in blocking:
            loc = f" [{c.get('file', '')}:{c.get('line', '')}]" if c.get("file") else ""
            parts.append(f"  [{c.get('persona', '?')} reviewer{loc}] {c.get('content', '')}")
    if suggestions:
        parts.append("\nSUGGESTIONS (should address):")
        for c in suggestions[:5]:
            parts.append(f"  - {c.get('content', '')}")

    if not parts:
        return "No specific feedback. Consider improving code quality, tests, and documentation."

    return "\n".join(parts)
