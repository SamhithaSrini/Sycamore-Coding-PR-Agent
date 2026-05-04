"""
Reviewer Agent — Mixture of Experts (Anthropic SDK)

Three specialized personas review independently, then synthesize.
OA direction #2: reviewer sees recent coder traces at inference time.
Anti-collapse guard: must justify every approval substantively.
"""

import json
import os
import re
from pathlib import Path
import anthropic

AGENT_DIR = Path("agents/reviewer")
TRACES_DIR = Path("data/traces")

PERSONAS = {
    "correctness": {
        "focus": "Logic errors, edge cases, off-by-one errors, algorithm correctness, "
                 "data integrity, type errors, missing null/empty checks",
        "weight": 0.50,
    },
    "security": {
        "focus": "Injection vulnerabilities, unsafe eval/exec, credential exposure, "
                 "input validation, path traversal, unsafe deserialization",
        "weight": 0.30,
    },
    "architecture": {
        "focus": "Code structure, naming clarity, abstraction quality, test coverage, "
                 "documentation, DRY violations, separation of concerns",
        "weight": 0.20,
    },
}

_client = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic()
    return _client


def _call_json(system: str, user: str, model: str, temperature: float = 0.1) -> dict:
    """Call Claude and parse JSON response. Returns {} on parse failure."""
    full_user = user + "\n\nReturn ONLY valid JSON. No markdown fences, no explanation text."
    response = _get_client().messages.create(
        model=model,
        max_tokens=2048,
        system=system,
        messages=[{"role": "user", "content": full_user}],
        temperature=temperature,
    )
    text = response.content[0].text
    return _extract_json(text)


def _extract_json(text: str) -> dict:
    """Robustly extract JSON from Claude response."""
    try:
        return json.loads(text)
    except Exception:
        pass
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except Exception:
            pass
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            pass
    return {"decision": "request_changes", "confidence": 0.5, "comments": [], "self_critique": "parse error"}


def _read(path: Path) -> str:
    return path.read_text() if path.exists() else ""


def _load_recent_coder_patterns(n_traces: int = 15) -> str:
    """OA direction #2: reviewer sees coder traces at inference time."""
    if not TRACES_DIR.exists():
        return "No coder traces available yet."
    trace_files = sorted(TRACES_DIR.glob("*.json"), key=lambda f: f.stat().st_mtime, reverse=True)[:n_traces]
    mistakes = []
    for tf in trace_files:
        try:
            data = json.loads(tf.read_text())
            cb = data.get("confidence", {})
            if cb.get("final_reward", 1.0) < 0.5:
                desc = (data.get("final_pr") or {}).get("description", "")
                if desc:
                    mistakes.append(desc[:150])
            if (cb.get("reviewer_coder_alignment") or 1) < 0.4:
                mistakes.append("Coder previously ignored reviewer feedback — be explicit about required changes")
        except Exception:
            continue
    if not mistakes:
        return "No notable coder patterns observed yet."
    lines = ["Recent coder behavior from traces:"]
    seen = set()
    for m in mistakes[:5]:
        if m not in seen:
            lines.append(f"  - {m}")
            seen.add(m)
    return "\n".join(lines)


def review_pr(pr: dict, issue: dict, model: str = None) -> dict:
    """MoE review: three personas independently, then synthesize."""
    model = model or os.getenv("REVIEWER_MODEL", "claude-haiku-4-5-20251001")
    rubric = _read(AGENT_DIR / "RUBRIC.md")
    calibration = _read(AGENT_DIR / "CALIBRATION.md")
    learned_patterns = _read(AGENT_DIR / "LEARNED_PATTERNS.md")
    constitution = _read(AGENT_DIR / "CONSTITUTION.md")
    coder_patterns = _load_recent_coder_patterns()

    persona_reviews = {}
    for name, config in PERSONAS.items():
        persona_reviews[name] = _run_persona_review(
            name, config, pr, issue, rubric, calibration,
            learned_patterns, constitution, coder_patterns, model
        )

    synthesized = _synthesize_reviews(persona_reviews)
    consensus = _compute_consensus(persona_reviews)

    # Anti-collapse guard
    if synthesized["decision"] == "approve" and not synthesized["blocking_comments"]:
        synthesized = _force_substantive_review(synthesized, pr, issue, model)

    return {
        "decision": synthesized["decision"],
        "comments": synthesized["all_comments"],
        "blocking_comments": synthesized["blocking_comments"],
        "reviewer_confidence": synthesized["confidence"],
        "persona_consensus": consensus,
        "persona_reviews": persona_reviews,
        "self_critique": synthesized.get("self_critique", ""),
    }


def _run_persona_review(
    persona_name, persona_config, pr, issue, rubric, calibration,
    learned_patterns, constitution, coder_patterns, model
) -> dict:
    system = f"""You are a specialized code reviewer focused on: {persona_config['focus']}

## Reviewer Rubric
{rubric}

## Calibration Notes
{calibration}

## Learned Patterns From Prior Traces
{learned_patterns}

## Review Constitution
{constitution}

## Recent Coder Patterns
{coder_patterns}

You MUST provide specific, actionable comments. Vague feedback is not acceptable.
If approving, explain in 3+ specific sentences exactly why the code is correct."""

    user = f"""Issue: {issue['title']}
{issue['body']}

PR Description: {pr.get('description', '')}
Linter passed: {pr.get('linter_passed', 'unknown')}

Diff:
```diff
{pr['diff']}
```

Review from your specialized perspective. Output JSON:
{{
  "decision": "approve" or "request_changes",
  "confidence": 0.0-1.0,
  "self_critique": "...",
  "comments": [
    {{
      "line": null or integer,
      "file": null or "filename.py",
      "severity": "blocking" or "suggestion" or "nitpick",
      "category": "correctness" or "security" or "style" or "architecture",
      "content": "specific actionable feedback",
      "confidence": 0.0-1.0
    }}
  ]
}}"""

    result = _call_json(system, user, model, temperature=0.1)
    if not isinstance(result, dict):
        result = {"decision": "request_changes", "confidence": 0.5, "comments": [], "self_critique": "parse error"}
    return result


def _compute_consensus(persona_reviews: dict) -> float:
    decisions = [r.get("decision", "request_changes") for r in persona_reviews.values()]
    approve_count = decisions.count("approve")
    n = len(decisions)
    return abs(approve_count - n / 2) / (n / 2)


def _synthesize_reviews(persona_reviews: dict) -> dict:
    weighted_approve = sum(
        (1 if r.get("decision") == "approve" else 0) * PERSONAS[p]["weight"]
        for p, r in persona_reviews.items()
    )
    decision = "approve" if weighted_approve >= 0.5 else "request_changes"

    all_comments, blocking_comments = [], []
    for persona, review in persona_reviews.items():
        for c in review.get("comments", []):
            enriched = dict(c)
            enriched["persona"] = persona
            all_comments.append(enriched)
            if c.get("severity") == "blocking":
                blocking_comments.append(enriched)

    avg_confidence = sum(r.get("confidence", 0.5) for r in persona_reviews.values()) / len(persona_reviews)

    return {
        "decision": decision,
        "all_comments": all_comments,
        "blocking_comments": blocking_comments,
        "confidence": avg_confidence,
        "self_critique": "Synthesized from MoE personas via weighted voting.",
    }


def _force_substantive_review(synthesized: dict, pr: dict, issue: dict, model: str) -> dict:
    """Anti-collapse: force a justification or find an issue before approving."""
    system = "You are a strict code reviewer. You must either find a concrete improvement or justify approval in specific detail."
    user = f"""You were about to approve this PR with no blocking issues.
Before approving, either:
(a) Find at least one concrete improvement, OR
(b) Explain in 3+ specific sentences exactly why each aspect is correct.

PR diff:
```diff
{pr['diff']}
```
Issue: {issue['title']}

Output JSON: {{"decision": "approve" or "request_changes", "justification": "...", "additional_comments": []}}"""

    result = _call_json(system, user, model, temperature=0.1)
    for c in result.get("additional_comments", []):
        if isinstance(c, str):
            c = {"content": c}
        elif not isinstance(c, dict):
            continue
        c["persona"] = "anti_collapse_guard"
        c.setdefault("severity", "suggestion")
        c.setdefault("category", "correctness")
        c.setdefault("content", "")
        synthesized["all_comments"].append(c)
    synthesized["self_critique"] = result.get("justification", "")
    synthesized["decision"] = result.get("decision", "approve")
    return synthesized
