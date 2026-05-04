from dataclasses import dataclass, field, asdict, fields
from typing import List, Optional
from datetime import datetime
import json
import uuid


@dataclass
class ReviewComment:
    content: str
    severity: str                   # "blocking" | "suggestion" | "nitpick"
    category: str                   # "correctness" | "security" | "style" | "architecture"
    persona: str                    # which MoE persona generated this
    line: Optional[int] = None
    file: Optional[str] = None
    confidence: float = 0.8
    addressed_in_next_diff: Optional[bool] = None   # set by alignment scorer
    addressed_reason: Optional[str] = None


@dataclass
class PRAttempt:
    attempt_number: int
    diff: str
    description: str
    timestamp: str
    coder_self_critique: str
    linter_passed: bool
    static_analysis_issues: List[str] = field(default_factory=list)


@dataclass
class ReviewAttempt:
    attempt_number: int
    decision: str                       # "approve" | "request_changes"
    comments: List[ReviewComment]
    reviewer_confidence: float
    persona_consensus: float            # agreement across MoE personas 0-1
    timestamp: str
    self_critique: str = ""
    persona_reviews: dict = field(default_factory=dict)
    # Populated after the NEXT pr_attempt arrives (None on final round)
    alignment_score: Optional[float] = None     # addressed_comments / total_meaningful_comments
    alignment_detail: Optional[dict] = None     # {"addressed": [...], "not_addressed": [...]}


@dataclass
class ConfidenceBundle:
    # LLM Judge (independent evaluation model)
    judge_score: float
    judge_confidence: float
    judge_reasoning: str
    judge_dimensions: dict              # {"correctness": 0.8, "security": 0.9, ...}
    reward_hacking_detected: bool

    # Test suite (ground truth — never exposed to agents)
    test_pass_rate: float
    test_coverage_delta: float
    tests_added: int

    # Reviewer agent
    reviewer_confidence: float
    reviewer_consensus: float

    # RLHF preference model
    preference_score: float

    # Reviewer–Coder Alignment Score
    # alignment = overlap(review_comments, changes_in_next_diff)
    # high alignment → good reviewer + good coder responsiveness
    # low alignment → reviewer gave irrelevant comments OR coder ignored feedback
    reviewer_coder_alignment: Optional[float]   # avg across all revision rounds; None if only 1 round
    alignment_interpretation: str               # "high" | "partial" | "low" | "single_round"

    # Composite
    final_reward: float
    reward_uncertainty: float           # std dev across signals; high = don't train on this
    use_for_training: bool


@dataclass
class InteractionTrace:
    trace_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    issue_id: str = ""
    issue_title: str = ""
    issue_body: str = ""
    issue_labels: List[str] = field(default_factory=list)
    repo: str = "pallets/click"

    pr_attempts: List[PRAttempt] = field(default_factory=list)
    review_attempts: List[ReviewAttempt] = field(default_factory=list)

    final_pr: Optional[PRAttempt] = None
    final_decision: str = ""            # "approved" | "max_rounds_reached" | "failed"
    total_rounds: int = 0

    confidence: Optional[ConfidenceBundle] = None

    # Training metadata — tracks which model version produced this trace
    coder_model_version: str = ""
    reviewer_model_version: str = ""
    training_cycle: int = 0

    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    def save(self, path: str):
        with open(path, "w") as f:
            f.write(self.to_json())

    @classmethod
    def from_dict(cls, data: dict) -> "InteractionTrace":
        # Reconstruct nested dataclasses
        pr_attempts = [PRAttempt(**p) for p in data.get("pr_attempts", [])]
        review_attempts = []
        for r in data.get("review_attempts", []):
            comments = [ReviewComment(**c) for c in r.get("comments", [])]
            r = dict(r)
            r["comments"] = comments
            review_attempts.append(ReviewAttempt(**r))
        confidence = None
        if data.get("confidence"):
            confidence_fields = {f.name for f in fields(ConfidenceBundle)}
            confidence = ConfidenceBundle(**{
                k: v for k, v in data["confidence"].items()
                if k in confidence_fields
            })
        final_pr = PRAttempt(**data["final_pr"]) if data.get("final_pr") else None
        return cls(
            **{k: v for k, v in data.items()
               if k not in ("pr_attempts", "review_attempts", "confidence", "final_pr")},
            pr_attempts=pr_attempts,
            review_attempts=review_attempts,
            confidence=confidence,
            final_pr=final_pr,
        )


@dataclass
class PreferencePair:
    pair_id: str
    issue_id: str
    source: str                     # "git_history" | "trace_comparison"
    chosen_diff: str
    chosen_reward: float
    chosen_reasoning: str
    rejected_diff: str
    rejected_reward: float
    rejected_reasoning: str
    confidence: float
    test_pass_delta: float
    judge_score_delta: float
    reward_source_weights: dict
