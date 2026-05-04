"""
Analysis — generates improvement curves and failure mode reports.

Run after all training cycles complete:
  python -m evaluation.analysis
"""

import json
from pathlib import Path


def print_metrics_table(metrics_history: list):
    """Print a formatted table of metrics across cycles."""
    if not metrics_history:
        print("No metrics history found.")
        return

    cols = [
        ("cycle", "Cycle"),
        ("avg_final_reward", "Avg Reward"),
        ("resolution_rate_le2_rounds", "Resolve ≤2r"),
        ("avg_test_pass_rate", "Test Pass"),
        ("reviewer_accuracy", "Rev Acc"),
        ("reviewer_coder_alignment", "Alignment"),
        ("reward_hacking_rate", "Hack Rate"),
        ("held_out_avg_reward", "Held-Out"),
    ]

    header = "  ".join(f"{label:>12}" for _, label in cols)
    print("\n" + "=" * len(header))
    print("TRAINING METRICS BY CYCLE")
    print("=" * len(header))
    print(header)
    print("-" * len(header))

    for m in metrics_history:
        row = "  ".join(
            f"{_fmt(m.get(key)):>12}" for key, _ in cols
        )
        print(row)

    print("=" * len(header))

    # Improvement summary
    if len(metrics_history) >= 2:
        first = metrics_history[0]
        last = metrics_history[-1]
        print("\nImprovement (cycle 1 → last):")
        for key, label in cols[1:]:
            v1 = first.get(key)
            vl = last.get(key)
            if v1 is not None and vl is not None:
                delta = vl - v1
                sign = "+" if delta >= 0 else ""
                print(f"  {label:>16}: {_fmt(v1)} → {_fmt(vl)} ({sign}{_fmt(delta)})")


def generate_failure_report(traces_dir: str = "data/traces") -> dict:
    """Analyze collected traces for failure patterns."""
    path = Path(traces_dir)
    if not path.exists():
        return {}

    traces = []
    for f in path.glob("*.json"):
        try:
            traces.append(json.loads(f.read_text()))
        except Exception:
            continue

    if not traces:
        return {}

    # Failure mode tallies
    reward_hacking = sum(
        1 for t in traces
        if t.get("confidence", {}).get("reward_hacking_detected")
    )
    max_rounds_hit = sum(
        1 for t in traces if t.get("final_decision") == "max_rounds_reached"
    )
    low_alignment = sum(
        1 for t in traces
        if t.get("confidence", {}).get("alignment_interpretation") == "low"
    )
    high_uncertainty = sum(
        1 for t in traces
        if t.get("confidence", {}).get("reward_uncertainty", 0) >= 0.25
    )
    reviewer_collapse_approvals = sum(
        1 for t in traces
        if t.get("total_rounds") == 1 and t.get("final_decision") == "approved"
    )

    report = {
        "total_traces": len(traces),
        "reward_hacking_count": reward_hacking,
        "max_rounds_hit": max_rounds_hit,
        "low_alignment_count": low_alignment,
        "high_uncertainty_count": high_uncertainty,
        "round1_approvals": reviewer_collapse_approvals,
        "round1_approval_rate": reviewer_collapse_approvals / len(traces),
    }

    print("\nFAILURE MODE REPORT")
    print("=" * 50)
    for k, v in report.items():
        print(f"  {k}: {v}")

    return report


def _fmt(v) -> str:
    if v is None:
        return "N/A"
    if isinstance(v, float):
        return f"{v:.3f}"
    return str(v)


if __name__ == "__main__":
    metrics_path = Path("data/metrics_history.json")
    if metrics_path.exists():
        history = json.loads(metrics_path.read_text())
        print_metrics_table(history)
    else:
        print("No metrics_history.json found. Run scripts/run_training_cycle.py first.")

    generate_failure_report()
