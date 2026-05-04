"""
Standalone Evaluation Script

Run after training cycles to generate a full report.
Usage:
  python scripts/evaluate.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from evaluation.analysis import print_metrics_table, generate_failure_report
from evaluation.metrics import compute_all_metrics
from learning.signal_extractor import load_all_traces


def main():
    print("=" * 60)
    print("Sycamore Evaluation Report")
    print("=" * 60)

    # Metrics history (from training cycles)
    metrics_path = Path("data/metrics_history.json")
    if metrics_path.exists():
        history = json.loads(metrics_path.read_text())
        print_metrics_table(history)
    else:
        print("No metrics_history.json. Recomputing from traces...")
        traces = load_all_traces()
        if traces:
            metrics = compute_all_metrics(traces)
            metrics["cycle"] = "all"
            print_metrics_table([metrics])
        else:
            print("No traces found.")

    generate_failure_report()

    # Alignment breakdown
    traces = load_all_traces()
    multi_round = [t for t in traces if t.get("total_rounds", 1) > 1]
    if multi_round:
        print(f"\nAlignment Score Analysis ({len(multi_round)} multi-round traces):")
        scores = [
            t["confidence"]["reviewer_coder_alignment"]
            for t in multi_round
            if t.get("confidence") and t["confidence"].get("reviewer_coder_alignment") is not None
        ]
        if scores:
            avg = sum(scores) / len(scores)
            high = sum(1 for s in scores if s >= 0.8)
            low = sum(1 for s in scores if s < 0.4)
            print(f"  avg alignment: {avg:.3f}")
            print(f"  high (≥0.8):   {high} ({high/len(scores):.0%})")
            print(f"  low  (<0.4):   {low} ({low/len(scores):.0%})")
            print(f"  Interpretation: high = both agents behaving well")
            print(f"                  low  = reviewer irrelevant or coder ignoring feedback")


if __name__ == "__main__":
    main()
