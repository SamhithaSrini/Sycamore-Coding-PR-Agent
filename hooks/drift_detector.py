"""
Drift Detector — anti-pathology hooks for the interaction loop.

Detects:
  reviewer collapse:       > 70% round-1 approval rate (reviewer too lenient)
  adversarial strictness:  > 95% rejection rate (reviewer too strict)
  mode collapse:           low persona consensus across many traces
  distributional shift:    rising gap between reviewer decision and GT

When collapse is detected, CALIBRATION.md is force-updated.
"""

from collections import deque
from pathlib import Path
from learning.prompt_updater import _compact_calibration

# Rolling windows (in-process state — reset between runs)
_round1_approval_window: deque = deque(maxlen=20)
_decision_window: deque = deque(maxlen=20)
_consensus_window: deque = deque(maxlen=20)
_reviewer_gt_disagreement_window: deque = deque(maxlen=20)


def check_reviewer_drift(trace) -> dict:
    """
    Call after each review attempt within the interaction loop.
    trace: InteractionTrace (or dict)
    Returns dict of any flags raised.
    """
    t = trace if isinstance(trace, dict) else trace.to_dict() if hasattr(trace, "to_dict") else {}
    reviews = t.get("review_attempts", []) or (trace.review_attempts if hasattr(trace, "review_attempts") else [])
    if not reviews:
        return {}

    latest = reviews[-1]
    latest_decision = (latest.get("decision") if isinstance(latest, dict) else latest.decision)
    latest_consensus = (latest.get("persona_consensus", 1.0) if isinstance(latest, dict) else latest.persona_consensus)
    total_rounds = t.get("total_rounds", 0) or getattr(trace, "total_rounds", 0)

    _decision_window.append(latest_decision)
    _consensus_window.append(latest_consensus)

    flags = {}

    # Round-1 approval tracking
    is_round1_approve = (
        len(reviews) == 1 and latest_decision == "approve"
        and (total_rounds == 0 or total_rounds == 1)
    )
    _round1_approval_window.append(1 if is_round1_approve else 0)

    if len(_round1_approval_window) >= 10:
        rate = sum(_round1_approval_window) / len(_round1_approval_window)
        if rate > 0.70:
            flags["reviewer_collapse"] = rate
            print(f"  Drift detector: REVIEWER COLLAPSE — {rate:.0%} round-1 approvals")
            _force_recalibration(
                f"Reviewer collapse: {rate:.0%} round-1 approval rate exceeds 70% threshold."
            )

    # Adversarial strictness
    if len(_decision_window) >= 10:
        reject_rate = list(_decision_window).count("request_changes") / len(_decision_window)
        if reject_rate > 0.95:
            flags["adversarial_strictness"] = reject_rate
            print(f"  Drift detector: ADVERSARIAL STRICTNESS — {reject_rate:.0%} rejection rate")
            _force_recalibration(
                f"Adversarial reviewer: {reject_rate:.0%} rejection rate. Be willing to approve good PRs."
            )

    # Low persona consensus (mode collapse indicator)
    if len(_consensus_window) >= 5:
        avg_consensus = sum(_consensus_window) / len(_consensus_window)
        if avg_consensus < 0.3:
            flags["mode_collapse_risk"] = avg_consensus
            print(f"  Drift detector: low persona consensus ({avg_consensus:.2f}) — mode collapse risk")

    return flags


def record_reviewer_gt_disagreement(reviewer_approved: bool, gt_good: bool):
    """
    Call after oracle evaluation to track reviewer accuracy over time.
    Detects distributional shift as coder improves.
    """
    agreed = (reviewer_approved == gt_good)
    _reviewer_gt_disagreement_window.append(1 if agreed else 0)

    if len(_reviewer_gt_disagreement_window) >= 10:
        accuracy = sum(_reviewer_gt_disagreement_window) / len(_reviewer_gt_disagreement_window)
        if accuracy < 0.6:
            print(f"  Drift detector: reviewer accuracy {accuracy:.0%} — potential distributional shift")
            _force_recalibration(
                f"Reviewer accuracy dropped to {accuracy:.0%}. "
                "Your calibration may not match the current coder distribution."
            )


def _force_recalibration(message: str):
    path = Path("agents/reviewer/CALIBRATION.md")
    existing = path.read_text() if path.exists() else ""
    path.write_text(_compact_calibration(existing + f"\n## AUTO-RECALIBRATION\n{message}\n"))
    print(f"  Drift detector: CALIBRATION.md updated")
