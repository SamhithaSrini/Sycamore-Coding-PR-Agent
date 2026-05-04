from learning.trace_collector import ConfidenceBundle
from learning.alignment import aggregate_alignment_scores
from typing import Optional, List


def build_confidence_bundle(
    oracle,
    judge_result: dict,
    reviewer_result: dict,
    test_result: dict,
    preference_score: float,
    round_alignment_scores: Optional[List[Optional[float]]] = None,
) -> ConfidenceBundle:
    alignment_avg, alignment_interp = aggregate_alignment_scores(
        round_alignment_scores or []
    )

    return ConfidenceBundle(
        judge_score=judge_result.get("overall_score", 0.0),
        judge_confidence=judge_result.get("confidence", 0.0),
        judge_reasoning=judge_result.get("reasoning", ""),
        judge_dimensions=judge_result.get("dimensions", {}),
        reward_hacking_detected=judge_result.get("reward_hacking_detected", False),

        test_pass_rate=test_result.get("pass_rate", 0.0),
        test_coverage_delta=test_result.get("coverage_delta", 0.0),
        tests_added=test_result.get("tests_added", 0),

        reviewer_confidence=reviewer_result.get("reviewer_confidence", 0.0),
        reviewer_consensus=reviewer_result.get("persona_consensus", 0.0),

        preference_score=preference_score,

        reviewer_coder_alignment=alignment_avg,
        alignment_interpretation=alignment_interp,

        final_reward=oracle.final_reward,
        reward_uncertainty=oracle.reward_uncertainty,
        use_for_training=oracle.use_for_training,
    )
