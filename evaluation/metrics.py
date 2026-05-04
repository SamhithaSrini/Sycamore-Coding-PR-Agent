"""
Evaluation Metrics

Primary metrics (tracked per training cycle):
  avg_final_reward           — composite ground truth score (main metric)
  resolution_rate_le2_rounds — % issues solved in ≤2 rounds (efficiency)
  avg_test_pass_rate         — direct GT signal (unfakeable)
  reviewer_accuracy          — % cases where reviewer aligned with GT
  reward_hacking_rate        — should stay near 0
  reviewer_coder_alignment   — NEW: avg alignment score across multi-round traces
  training_data_efficiency   — % traces usable for fine-tuning
  held_out_avg_reward        — most important: generalization to unseen issues
"""

from typing import List, Dict, Optional


def compute_all_metrics(traces: list, held_out_results: Optional[list] = None) -> Dict:
    """
    traces: list of trace dicts (from JSON).
    Returns metrics dict for one training cycle.
    """
    if not traces:
        return {}

    n = len(traces)

    # 1. Resolution rate: approved in ≤2 rounds
    resolution_rate = sum(
        1 for t in traces
        if t.get("total_rounds", 99) <= 2 and t.get("final_decision") == "approved"
    ) / n

    # 2. Average final reward
    rewards = [t["confidence"]["final_reward"] for t in traces if t.get("confidence")]
    avg_reward = _mean(rewards)

    # 3. Test pass rate
    test_rates = [t["confidence"]["test_pass_rate"] for t in traces if t.get("confidence")]
    avg_test_pass = _mean(test_rates)

    # 4. Reviewer accuracy (% times reviewer decision aligned with GT)
    reviewer_correct = sum(
        1 for t in traces
        if t.get("confidence") and (
            (t.get("final_decision") == "approved")
            == (t["confidence"].get("final_reward", 0) > 0.7)
        )
    )
    reviewer_accuracy = reviewer_correct / n

    # 5. Reward hacking rate
    hacking_rate = sum(
        1 for t in traces
        if t.get("confidence") and t["confidence"].get("reward_hacking_detected")
    ) / n

    # 6. Training data efficiency
    training_usable = sum(
        1 for t in traces
        if t.get("confidence") and t["confidence"].get("use_for_training")
    ) / n

    # 7. Reviewer–Coder Alignment Score (multi-round traces only)
    alignment_scores = [
        t["confidence"]["reviewer_coder_alignment"]
        for t in traces
        if t.get("confidence") and t["confidence"].get("reviewer_coder_alignment") is not None
    ]
    avg_alignment = _mean(alignment_scores)

    # 8. Average rounds per resolution
    round_counts = [t.get("total_rounds", MAX_ROUNDS) for t in traces]
    avg_rounds = _mean(round_counts)

    # 9. Held-out evaluation (most important — never trained on)
    held_out_reward = None
    if held_out_results:
        held_rewards = [
            r["confidence"]["final_reward"]
            for r in held_out_results
            if r.get("confidence")
        ]
        held_out_reward = _mean(held_rewards)

    return {
        "avg_final_reward": avg_reward,
        "resolution_rate_le2_rounds": resolution_rate,
        "avg_test_pass_rate": avg_test_pass,
        "reviewer_accuracy": reviewer_accuracy,
        "reward_hacking_rate": hacking_rate,
        "training_data_efficiency": training_usable,
        "reviewer_coder_alignment": avg_alignment,
        "avg_rounds_per_issue": avg_rounds,
        "held_out_avg_reward": held_out_reward,
        "n_traces": n,
        "n_multi_round": sum(1 for t in traces if t.get("total_rounds", 1) > 1),
        "n_alignment_computed": len(alignment_scores),
    }


def _mean(values: list) -> Optional[float]:
    valid = [v for v in values if v is not None]
    return sum(valid) / len(valid) if valid else None


MAX_ROUNDS = 4  # Default; matches env var default
