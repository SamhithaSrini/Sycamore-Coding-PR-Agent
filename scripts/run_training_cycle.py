"""
Main Orchestration Script

Full training cycle:
  1. Load issues
  2. Run interaction loop on training issues
  3. Extract training signals (reward, alignment, debate)
  4. Update firmware (.md files: SKILLS, RUBRIC, CALIBRATION, few-shot bank)
  5. Fine-tune models (when enough data)
  6. Evaluate on held-out issues
  7. Compute and log metrics

Usage:
  python scripts/run_training_cycle.py [--cycles N] [--issues-per-cycle N]
"""

import argparse
import json
import os
import sys
from pathlib import Path

# Make root importable
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from core.interaction_loop import run_interaction
from learning.finetuning import run_finetune_cycle
from learning.rlhf_pipeline import extract_preference_pairs_from_git
from learning.prompt_updater import update_skills_md, update_rubric_md, update_calibration_md, update_few_shot_bank
from learning.signal_extractor import extract_training_signals, load_all_traces
from evaluation.metrics import compute_all_metrics
from evaluation.held_out_eval import run_held_out_evaluation
from evaluation.analysis import print_metrics_table, generate_failure_report


def load_issues(path: Path) -> list:
    issues = []
    for f in sorted(path.glob("*.json")):
        try:
            issues.append(json.loads(f.read_text()))
        except Exception as e:
            print(f"  Warning: could not load issue {f}: {e}")
    return issues


def main():
    parser = argparse.ArgumentParser(description="Run Sycamore training cycles")
    parser.add_argument("--cycles", type=int, default=3)
    parser.add_argument("--issues-per-cycle", type=int, default=5)
    parser.add_argument("--held-out-per-cycle", type=int, default=3)
    parser.add_argument("--issues-path", default="data/issues")
    parser.add_argument("--held-out-path", default="data/held_out")
    parser.add_argument("--skip-firmware", action="store_true")
    parser.add_argument("--no-save-training-traces", action="store_true")
    parser.add_argument("--metrics-output", default="data/metrics_history.json")
    args = parser.parse_args()

    print("=" * 60)
    print("Sycamore Co-Optimization System")
    print("=" * 60)

    # ── Bootstrap RLHF pairs from git history ─────────────────────
    repo_path = os.getenv("REPO_PATH", "/tmp/click")
    pairs_path = Path("data/preference_pairs/pairs.json")
    if Path(repo_path).exists() and not pairs_path.exists():
        print("\nExtracting RLHF pairs from git history...")
        pairs = extract_preference_pairs_from_git(repo_path)
        pairs_path.parent.mkdir(parents=True, exist_ok=True)
        pairs_path.write_text(json.dumps(pairs, indent=2))
        print(f"  Extracted {len(pairs)} preference pairs")

    # ── Load issues ───────────────────────────────────────────────
    training_issues = load_issues(Path(args.issues_path))
    held_out_issues = load_issues(Path(args.held_out_path))

    if not training_issues:
        print("\nNo training issues found. Run scripts/bootstrap_repo.py first.")
        sys.exit(1)

    print(f"\nIssues: {len(training_issues)} training, {len(held_out_issues)} held-out")
    metrics_history = []

    for cycle in range(1, args.cycles + 1):
        print(f"\n{'='*60}")
        print(f"TRAINING CYCLE {cycle}/{args.cycles}")
        print(f"{'='*60}")

        # Select issues for this cycle
        start = (cycle - 1) * args.issues_per_cycle
        cycle_issues = training_issues[start: start + args.issues_per_cycle]
        if not cycle_issues:
            # Wrap around if more cycles than issues
            cycle_issues = training_issues[:args.issues_per_cycle]

        print(f"Issues this cycle: {len(cycle_issues)}")

        # ── Run interactions ──────────────────────────────────────
        cycle_traces = []
        for i, issue in enumerate(cycle_issues):
            print(f"\n[{i+1}/{len(cycle_issues)}] {issue.get('title', '')[:70]}")
            try:
                trace = run_interaction(
                    issue,
                    training_cycle=cycle,
                    save_training_trace=not args.no_save_training_traces,
                )
                cycle_traces.append(trace)
            except Exception as e:
                print(f"  Error: {e}")
                import traceback; traceback.print_exc()

        # Load all traces (including from previous cycles)
        all_trace_dicts = load_all_traces()

        if not cycle_traces:
            print("\nNo successful traces this cycle; skipping firmware updates and metrics.")
            continue

        # ── Extract signals ───────────────────────────────────────
        signals = extract_training_signals(all_trace_dicts)
        print(f"\nSignals: {signals['stats']}")

        # ── Update firmware ───────────────────────────────────────
        if args.skip_firmware:
            print("\nSkipping firmware updates (--skip-firmware).")
        else:
            print("\nUpdating agent firmware...")
            update_skills_md(signals, cycle)
            update_rubric_md(signals, cycle)
            update_calibration_md(signals, cycle)
            update_few_shot_bank(signals)

        # ── Fine-tune ─────────────────────────────────────────────
        min_examples = int(os.getenv("MIN_POSITIVE_EXAMPLES_FOR_FINETUNE", "5"))
        if len(signals["coder_positive"]) >= min_examples:
            print("\nRunning fine-tuning...")
            run_finetune_cycle(cycle)
        else:
            print(f"\nSkipping fine-tune: only {len(signals['coder_positive'])} positive examples "
                  f"(need {min_examples})")

        # ── Held-out evaluation ────────────────────────────────────
        held_out_results = []
        if held_out_issues and args.held_out_per_cycle > 0:
            held_out_results = run_held_out_evaluation(
                held_out_issues[:args.held_out_per_cycle],
                cycle,
            )

        # ── Compute metrics ────────────────────────────────────────
        cycle_trace_dicts = []
        for t in cycle_traces:
            trace_path = Path("data/traces") / f"{t.trace_id}.json"
            if trace_path.exists():
                cycle_trace_dicts.append(json.loads(trace_path.read_text()))
            else:
                cycle_trace_dicts.append(t.to_dict())
        metrics = compute_all_metrics(cycle_trace_dicts, held_out_results)
        metrics["cycle"] = cycle
        metrics_history.append(metrics)

        print(f"\nCycle {cycle} metrics:")
        for k, v in metrics.items():
            if v is not None and k != "cycle":
                val = f"{v:.3f}" if isinstance(v, float) else str(v)
                print(f"  {k}: {val}")

    # ── Save metrics history ───────────────────────────────────────
    out_path = Path(args.metrics_output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(metrics_history, indent=2))
    print(f"\nMetrics saved: {out_path}")

    # ── Final analysis ────────────────────────────────────────────
    print_metrics_table(metrics_history)
    generate_failure_report()
    print("\nDone. Run `python -m evaluation.analysis` for detailed report.")


if __name__ == "__main__":
    main()
