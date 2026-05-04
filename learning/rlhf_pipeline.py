"""
RLHF Pipeline — mines git history for implicit human preference signals.

Preference scoring uses Jaccard token-overlap similarity (no embeddings API needed).
Anthropic does not provide an embeddings API, so we use a lexical similarity proxy.
"""

import json
import os
import re
import subprocess
import uuid
from pathlib import Path
from typing import List, Optional


def extract_preference_pairs_from_git(repo_path: str) -> List[dict]:
    """Mine git history for implicit human preference signals."""
    repo = Path(repo_path)
    if not repo.exists():
        print(f"  RLHF: repo not found at {repo_path}")
        return []

    pairs = []
    prs = _get_merge_commits(repo)
    print(f"  RLHF: found {len(prs)} merge commits to analyze")

    for pr in prs[:50]:
        diff = _get_pr_diff(repo, pr["commit_hash"])
        if not diff or len(diff) < 100:
            continue
        message_quality = min(len(pr.get("message", "")) / 500, 1.0)
        pairs.append({
            "pair_id": str(uuid.uuid4()),
            "issue_id": pr.get("pr_number", "git"),
            "source": "git_history",
            "chosen_diff": diff[:4000],
            "chosen_reward": 0.7 + 0.3 * message_quality,
            "chosen_reasoning": f"Merged PR from git history. Quality score: {message_quality:.2f}",
            "rejected_diff": "",
            "rejected_reward": 0.3,
            "rejected_reasoning": "Hypothetical lower-quality alternative",
            "confidence": 0.6,
            "test_pass_delta": 0.0,
            "judge_score_delta": 0.2 * message_quality,
            "lean_verified_chosen": None,
            "lean_verified_rejected": None,
            "reward_source_weights": {"tests": 0.4, "lean": 0.25, "judge": 0.25, "preference": 0.1},
        })

    return pairs


def score_preference(diff: str, issue: dict) -> float:
    """
    Score a new diff against high-quality PRs from preference pairs.
    Uses Jaccard token-overlap similarity — no embeddings API needed.
    Returns 0.5 (neutral) if no preference data exists yet.
    """
    pairs_path = Path("data/preference_pairs/pairs.json")
    if not pairs_path.exists() or not diff.strip():
        return 0.5

    try:
        pairs = json.loads(pairs_path.read_text())
    except Exception:
        return 0.5

    chosen_diffs = [
        p["chosen_diff"] for p in pairs
        if p.get("chosen_diff") and p.get("confidence", 0) > 0.5
    ]
    if not chosen_diffs:
        return 0.5

    query_tokens = set(diff.lower().split())
    if not query_tokens:
        return 0.5

    similarities = []
    for ref in chosen_diffs[:15]:
        ref_tokens = set(ref.lower().split())
        if not ref_tokens:
            continue
        intersection = len(query_tokens & ref_tokens)
        union = len(query_tokens | ref_tokens)
        similarities.append(intersection / union if union > 0 else 0.0)

    return sum(similarities) / len(similarities) if similarities else 0.5


def _get_merge_commits(repo: Path) -> List[dict]:
    result = subprocess.run(
        ["git", "log", "--merges", "--oneline", "-100",
         "--pretty=format:%H|%s|%cd", "--date=short"],
        cwd=repo, capture_output=True, text=True, timeout=30
    )
    prs = []
    for line in result.stdout.splitlines():
        parts = line.split("|", 2)
        if len(parts) < 2:
            continue
        commit_hash, message = parts[0], parts[1]
        pr_match = re.search(r"#(\d+)", message)
        prs.append({
            "commit_hash": commit_hash,
            "message": message,
            "pr_number": pr_match.group(1) if pr_match else commit_hash[:8],
        })
    return prs


def _get_pr_diff(repo: Path, commit_hash: str) -> Optional[str]:
    result = subprocess.run(
        ["git", "show", "--stat", "--patch", commit_hash],
        cwd=repo, capture_output=True, text=True, timeout=30
    )
    if result.returncode != 0:
        return None
    return result.stdout[:6000]
