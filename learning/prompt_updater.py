"""
Prompt Updater — writes bounded, grounded learning memories after each cycle.

The agents improve through deterministic firmware:
  - coder few-shot examples from high-reward source-changing PRs
  - coder failure rules from reward-hacked / low-reward traces
  - reviewer calibration from decisions that agreed or disagreed with ground truth
  - compact alignment notes for coder/reviewer co-optimization
"""

import json
from collections import Counter
from pathlib import Path


CODER_MEMORY = Path("agents/coder/LEARNED_PATTERNS.md")
REVIEWER_MEMORY = Path("agents/reviewer/LEARNED_PATTERNS.md")


def update_skills_md(signals: dict, training_cycle: int):
    """Update coder memory from grounded positive and negative traces."""
    content = _build_coder_memory(signals, training_cycle)
    CODER_MEMORY.write_text(content)
    print(f"  Coder learned patterns updated: {CODER_MEMORY}")


def update_rubric_md(signals: dict, training_cycle: int):
    """Update reviewer memory from ground-truth confirmed review outcomes."""
    content = _build_reviewer_memory(signals, training_cycle)
    REVIEWER_MEMORY.write_text(content)
    print(f"  Reviewer learned patterns updated: {REVIEWER_MEMORY}")


def update_calibration_md(signals: dict, training_cycle: int):
    path = Path("agents/reviewer/CALIBRATION.md")
    current = path.read_text() if path.exists() else ""
    low_align = [s for s in signals.get("alignment_signals", []) if s["interpretation"] == "low"]
    if not low_align:
        return

    reviewer_fault = [s for s in low_align if s.get("gt_good")]
    coder_fault = [s for s in low_align if not s.get("gt_good")]

    note = f"\n## Cycle {training_cycle} Auto-Calibration\n"
    if reviewer_fault:
        note += (f"- {len(reviewer_fault)} trace(s): low alignment but good outcome — "
                 "reviewer comments were likely irrelevant or non-actionable.\n")
    if coder_fault:
        note += (f"- {len(coder_fault)} trace(s): low alignment and bad outcome — "
                 "coder likely ignored valid feedback; reviewer should make blocking changes explicit.\n")

    path.write_text(_compact_calibration(current + note))
    print(f"  CALIBRATION.md updated for cycle {training_cycle}")


def update_few_shot_bank(signals: dict, max_examples: int = 20):
    bank_path = Path("agents/coder/few_shot_bank.json")
    existing = json.loads(bank_path.read_text()) if bank_path.exists() else []

    new_examples = [
        {
            "issue": ex["issue"],
            "issue_title": ex.get("issue_title", ""),
            "diff": ex["diff"][:3000],
            "description": ex.get("description", ""),
            "judge_score": ex["reward"],
            "rounds_needed": ex.get("rounds_needed", 1),
            "source_files": ex.get("source_files", []),
            "test_files": ex.get("test_files", []),
        }
        for ex in signals.get("coder_positive", [])
        if ex.get("diff") and ex.get("has_source_changes") and not ex.get("is_test_only")
    ]

    deduped = {}
    for ex in existing + new_examples:
        key = (ex.get("issue_title", ""), ex.get("diff", "")[:500])
        if key not in deduped or ex.get("judge_score", 0) > deduped[key].get("judge_score", 0):
            deduped[key] = ex

    top = sorted(deduped.values(), key=lambda x: x.get("judge_score", 0), reverse=True)[:max_examples]
    bank_path.write_text(json.dumps(top, indent=2))
    print(f"  Few-shot bank: {len(top)} examples")


def _build_coder_memory(signals: dict, training_cycle: int, max_items: int = 6) -> str:
    positives = [
        ex for ex in signals.get("coder_positive", [])
        if ex.get("has_source_changes") and not ex.get("is_test_only")
    ]
    negatives = signals.get("coder_negative", [])
    reason_counts = Counter(ex.get("reason", "unknown") for ex in negatives)

    lines = [
        "# Coder Learned Patterns",
        "",
        f"Updated through cycle {training_cycle}. These rules come only from training traces, never held-out traces.",
        "",
        "## Current Failure Rules",
    ]

    if reason_counts:
        for reason, count in reason_counts.most_common(max_items):
            lines.append(f"- {reason}: observed {count} time(s). {_coder_rule_for_reason(reason)}")
    else:
        lines.append("- No grounded failure patterns yet.")

    lines.extend(["", "## Successful Patch Patterns"])
    if positives:
        for ex in sorted(positives, key=lambda item: item.get("reward", 0), reverse=True)[:max_items]:
            files = ", ".join(ex.get("source_files", [])[:3]) or "source file"
            tests = ", ".join(ex.get("test_files", [])[:2]) or "no test file recorded"
            lines.append(
                f"- reward={ex.get('reward', 0):.2f}; issue={_clip(ex.get('issue_title', 'unknown'), 90)}; "
                f"source={files}; tests={tests}"
            )
    else:
        lines.append("- No high-reward source-changing examples yet. Prefer source changes plus targeted tests.")

    lines.extend(["", "## Recent Mistakes To Learn From"])
    if negatives:
        for ex in negatives[:max_items]:
            lines.append(f"- issue={_clip(ex.get('issue_title', 'unknown'), 80)}")
            lines.append(f"  mistake={ex.get('reason', 'unknown')}: {_coder_rule_for_reason(ex.get('reason', 'unknown'))}")
            if ex.get("review_feedback"):
                lines.append(f"  reviewer_feedback={_clip('; '.join(ex['review_feedback']), 180)}")
            if ex.get("judge_reasoning"):
                lines.append(f"  judge_summary={_clip(ex.get('judge_reasoning', ''), 180)}")
            files = ", ".join(ex.get("source_files", [])[:3])
            if files:
                lines.append(f"  touched_source={files}")
    else:
        lines.append("- No grounded mistakes yet.")

    lines.extend([
        "",
        "## Non-Negotiable Submission Gate",
        "- Produce at least one source-code change for coding issues; test-only patches are failures.",
        "- Add or update tests only to verify a real implementation change.",
        "- Do not submit an empty diff, a description-only fix, or a patch that weakens/removes existing tests.",
        "- Use exact <change><file>/<old>/<new> blocks copied from provided source context.",
        "- Failure reasons from prior cycles are visible here on purpose; correct them in the next attempt.",
    ])
    return "\n".join(lines) + "\n"


def _build_reviewer_memory(signals: dict, training_cycle: int, max_items: int = 6) -> str:
    positives = signals.get("reviewer_positive", [])
    negatives = signals.get("reviewer_negative", [])
    debates = signals.get("debate_signals", [])
    negative_reasons = Counter(
        ex.get("reason") or ex.get("judge_reasoning", "gt disagreement")[:80]
        for ex in negatives
    )

    lines = [
        "# Reviewer Learned Patterns",
        "",
        f"Updated through cycle {training_cycle}. Use these as calibration memory, not as replacements for the rubric.",
        "",
        "## Grounded Calibration",
    ]

    lines.append(f"- Ground-truth confirmed review decisions: {len(positives)}.")
    lines.append(f"- Ground-truth contradicted review decisions/comments: {len(negatives)}.")
    for reason, count in negative_reasons.most_common(max_items):
        lines.append(f"- Watch for: {_clip(reason, 140)} ({count} case(s)).")

    lines.extend(["", "## Persona Debate Lessons"])
    if debates:
        for debate in debates[:max_items]:
            correct = ", ".join(debate.get("correct_personas", [])) or "none"
            wrong = ", ".join(debate.get("wrong_personas", [])) or "none"
            lines.append(
                f"- correct_decision={debate.get('correct_decision')}; "
                f"right_personas={correct}; wrong_personas={wrong}"
            )
    else:
        lines.append("- No persona disagreement with ground-truth resolution recorded yet.")

    lines.extend([
        "",
        "## Review Gate",
        "- Request changes for empty diffs, test-only patches, removed tests, or descriptions without implementation.",
        "- Approve only when the diff changes the relevant source behavior and tests meaningfully verify it.",
        "- If personas disagree, prefer the persona whose decision matches tests/judge-grounded outcomes in recent traces.",
    ])
    return "\n".join(lines) + "\n"


def _coder_rule_for_reason(reason: str) -> str:
    rules = {
        "empty_diff": "Always include concrete source changes; a description is not a PR.",
        "test_only_patch": "Do not alter tests without implementing the source fix.",
        "reward_hacking": "Optimize for real behavior and tests, not reviewer-satisfying prose.",
        "no_source_change": "Coding issues require source-code changes unless the issue is explicitly test-only.",
        "ignored_reviewer_feedback": "When revising, address each blocking comment directly.",
        "low_quality": "Reproduce the failure, make the smallest source change, and verify with tests.",
    }
    return rules.get(reason, "Inspect the failed trace before repeating this pattern.")


def _format_patterns(pos: list, neg: list, align: list) -> str:
    lines = []
    if pos:
        lines.append(f"Successful patterns ({len(pos)} examples):")
        for ex in pos[:3]:
            lines.append(f"  reward={ex.get('reward', 0):.2f}, rounds={ex.get('rounds_needed', 1)}")
    if neg:
        lines.append(f"\nFailure patterns ({len(neg)} examples):")
        for ex in neg[:3]:
            lines.append(f"  reason={ex.get('reason', '?')}")
    if align:
        high = sum(1 for s in align if s["interpretation"] == "high")
        low = sum(1 for s in align if s["interpretation"] == "low")
        lines.append(f"\nAlignment: {high} high, {low} low out of {len(align)} multi-round traces")
    return "\n".join(lines)


def _compact_calibration(content: str, max_auto_notes: int = 8) -> str:
    """Keep the reviewer memory bounded so repeated drift notes do not drown out signal."""
    sections = []
    current_header = None
    current_lines = []
    for line in content.splitlines():
        if line.startswith("## ") and current_header is not None:
            sections.append((current_header, "\n".join(current_lines).strip()))
            current_header = line
            current_lines = []
        elif line.startswith("## "):
            current_header = line
            current_lines = []
        elif current_header is None:
            sections.append((None, line))
        else:
            current_lines.append(line)
    if current_header is not None:
        sections.append((current_header, "\n".join(current_lines).strip()))

    intro = [body for header, body in sections if header is None and body.strip()]
    stable = [
        (header, body) for header, body in sections
        if header and "Auto-Calibration" not in header and header != "## AUTO-RECALIBRATION"
    ]
    auto = [
        (header, body) for header, body in sections
        if header and ("Auto-Calibration" in header or header == "## AUTO-RECALIBRATION")
    ]

    deduped_auto = []
    seen = set()
    for header, body in reversed(auto):
        key = (header, body)
        if key in seen:
            continue
        seen.add(key)
        deduped_auto.append((header, body))
        if len(deduped_auto) >= max_auto_notes:
            break
    deduped_auto.reverse()

    parts = [line for line in intro if line.strip()]
    for header, body in stable + deduped_auto:
        parts.append(header)
        if body:
            parts.append(body)
    return "\n\n".join(parts).strip() + "\n"


def _clip(text: str, limit: int) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= limit else text[: limit - 3] + "..."
