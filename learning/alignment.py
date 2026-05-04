"""
Reviewer–Coder Alignment Score
alignment = overlap(review_comments, changes_in_next_diff)

For each blocking/suggestion review comment, ask the LLM whether the next diff
addressed it. Score = addressed_count / total_meaningful_comments.

Training signal interpretation:
  high alignment (≥0.8) + high reward  → good reviewer + good coder → strong positive for both
  low alignment  (<0.4) + high reward  → reviewer gave irrelevant comments → reviewer negative
  low alignment  (<0.4) + low reward   → coder ignored valid feedback   → coder negative
  high alignment + low reward          → deeper problem; flag for human review
"""

import json
import os
import re
from typing import List, Optional
import anthropic
from learning.trace_collector import ReviewComment

_client = None
_MODEL = os.getenv("CODER_MODEL", "claude-haiku-4-5-20251001")  # cheap model fine for yes/no checks


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic()
    return _client


def compute_alignment(
    comments: List[ReviewComment],
    next_diff: str,
) -> dict:
    """
    Returns:
      score             float 0–1 (or None if no meaningful comments)
      addressed         list of ReviewComment with addressed_in_next_diff=True
      not_addressed     list of ReviewComment with addressed_in_next_diff=False
      interpretation    "high" | "partial" | "low" | "no_comments"
      training_signal   dict with recommended use for coder/reviewer training
    """
    meaningful = [c for c in comments if c.severity in ("blocking", "suggestion")]
    if not meaningful:
        return {
            "score": None,
            "addressed": [],
            "not_addressed": [],
            "interpretation": "no_comments",
            "training_signal": {"coder": "neutral", "reviewer": "neutral"},
        }

    addressed, not_addressed = [], []
    for comment in meaningful:
        result = _check_comment_addressed(comment, next_diff)
        comment.addressed_in_next_diff = result["addressed"]
        comment.addressed_reason = result["reason"]
        if result["addressed"]:
            addressed.append(comment)
        else:
            not_addressed.append(comment)

    total = len(meaningful)
    score = len(addressed) / total

    interpretation = "high" if score >= 0.8 else "partial" if score >= 0.4 else "low"

    return {
        "score": score,
        "addressed": addressed,
        "not_addressed": not_addressed,
        "interpretation": interpretation,
        "training_signal": _derive_training_signal(score, not_addressed),
    }


def _check_comment_addressed(comment: ReviewComment, diff: str) -> dict:
    """Single LLM call: did this diff address this review comment?"""
    loc = f" in `{comment.file}`" if comment.file else ""
    if comment.file and comment.line:
        loc += f" at line {comment.line}"

    response = _get_client().messages.create(
        model=_MODEL,
        max_tokens=256,
        messages=[{"role": "user", "content": f"""Did the following diff address this code review comment?

Review comment ({comment.severity}{loc}):
{comment.content}

Diff (truncated to 3000 chars):
```diff
{diff[:3000]}
```

Return ONLY valid JSON (no markdown):
{{"addressed": true or false, "reason": "one sentence explanation"}}"""}],
        temperature=0.0,
    )
    text = response.content[0].text
    try:
        # Direct parse
        return json.loads(text)
    except Exception:
        pass
    # Extract from text
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            pass
    return {"addressed": False, "reason": "parse error"}


def _derive_training_signal(score: float, not_addressed: List[ReviewComment]) -> dict:
    if score >= 0.8:
        return {"coder": "positive", "reviewer": "positive",
                "note": "High alignment — both agents behaving well"}
    elif score < 0.4:
        blocking_not_addressed = [c for c in not_addressed if c.severity == "blocking"]
        if blocking_not_addressed:
            return {"coder": "negative", "reviewer": "neutral",
                    "note": f"Coder ignored {len(blocking_not_addressed)} blocking comment(s)"}
        else:
            return {"coder": "neutral", "reviewer": "negative",
                    "note": "Reviewer suggestions were not acted on — may have been irrelevant"}
    else:
        return {"coder": "neutral", "reviewer": "neutral", "note": "Partial alignment — inconclusive"}


def aggregate_alignment_scores(round_scores: List[Optional[float]]) -> tuple:
    valid = [s for s in round_scores if s is not None]
    if not valid:
        return None, "single_round"
    avg = sum(valid) / len(valid)
    interp = "high" if avg >= 0.8 else "partial" if avg >= 0.4 else "low"
    return avg, interp
