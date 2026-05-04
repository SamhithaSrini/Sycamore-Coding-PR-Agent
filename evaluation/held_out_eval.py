"""
Held-Out Evaluation

Evaluates on a fixed set of issues never used in training.
This is the gold standard metric: it cannot be gamed by overfitting to training issues.
Run after each training cycle to detect both improvement and regression.
"""

import json
from pathlib import Path
from typing import List
from core.interaction_loop import run_interaction


def run_held_out_evaluation(issues: List[dict], training_cycle: int) -> List[dict]:
    """
    Run the full interaction loop on held-out issues.
    Returns list of trace dicts for metric computation.
    """
    print(f"\n  Held-out evaluation: {len(issues)} issues (cycle {training_cycle})")
    results = []

    for i, issue in enumerate(issues):
        print(f"    [{i+1}/{len(issues)}] {issue.get('title', '')[:60]}")
        try:
            trace = run_interaction(
                issue,
                training_cycle=training_cycle,
                save_training_trace=False,
            )
            trace_dict = json.loads(trace.to_json())
            trace_dict["is_held_out"] = True
            results.append(trace_dict)
        except Exception as e:
            print(f"    Error on held-out issue {issue.get('id', '?')}: {e}")

    if results:
        rewards = [r["confidence"]["final_reward"] for r in results if r.get("confidence")]
        avg = sum(rewards) / len(rewards) if rewards else 0.0
        print(f"  Held-out avg reward: {avg:.3f} (n={len(results)})")

    # Save held-out results separately
    held_out_dir = Path("data/held_out_results")
    held_out_dir.mkdir(parents=True, exist_ok=True)
    out_path = held_out_dir / f"cycle{training_cycle}_results.json"
    out_path.write_text(json.dumps(results, indent=2))

    return results
