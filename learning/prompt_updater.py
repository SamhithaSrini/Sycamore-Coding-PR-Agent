"""
Prompt Updater — updates agent firmware (.md files) after each training cycle.
Creates a human-readable audit trail of what each agent learned.
"""

import json
from pathlib import Path
import anthropic

_client = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic()
    return _client


def _call(user: str) -> str:
    response = _get_client().messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=2048,
        messages=[{"role": "user", "content": user}],
        temperature=0.2,
    )
    return response.content[0].text


def update_skills_md(signals: dict, training_cycle: int):
    path = Path("agents/coder/SKILLS.md")
    current = path.read_text() if path.exists() else ""
    summary = _format_patterns(signals.get("coder_positive", []),
                               signals.get("coder_negative", []),
                               signals.get("alignment_signals", []))
    if not summary.strip():
        return

    new_content = _call(f"""Current SKILLS.md:
{current}

New patterns from training cycle {training_cycle}:
{summary}

Update SKILLS.md to incorporate these learnings.
Add a "## Cycle {training_cycle} Updates" section at the bottom.
Add new skills from successful patterns, warnings about failure patterns.
Keep it concise and actionable.
Output only the updated SKILLS.md content.""")

    path.write_text(new_content)
    print(f"  SKILLS.md updated for cycle {training_cycle}")


def update_rubric_md(signals: dict, training_cycle: int):
    path = Path("agents/reviewer/RUBRIC.md")
    current = path.read_text() if path.exists() else ""
    wrong_cases = signals.get("reviewer_negative", [])
    if not wrong_cases:
        return

    wrong_summary = "\n".join(
        f"- Reviewer said '{c.get('reviewer_decision', '?')}', GT said '{c.get('gt_assessment', '?')}'. "
        f"Reason: {c.get('reason', c.get('judge_reasoning', ''))[:200]}"
        for c in wrong_cases[:5]
    )

    new_content = _call(f"""Current RUBRIC.md:
{current}

Cases where reviewer was wrong (cycle {training_cycle}):
{wrong_summary}

Update RUBRIC.md with a "## Cycle {training_cycle} Calibration" section.
Focus on what the reviewer should do differently to avoid these mistakes.
Output only the updated RUBRIC.md content.""")

    path.write_text(new_content)
    print(f"  RUBRIC.md updated for cycle {training_cycle}")


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
                 "reviewer comments were irrelevant or non-actionable. "
                 "Focus on concrete, specific feedback.\n")
    if coder_fault:
        note += (f"- {len(coder_fault)} trace(s): low alignment and bad outcome — "
                 "coder ignored reviewer feedback. Make blocking issues unambiguous.\n")

    path.write_text(current + note)
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
        }
        for ex in signals.get("coder_positive", [])
        if ex.get("diff")
    ]

    top = sorted(existing + new_examples, key=lambda x: x.get("judge_score", 0), reverse=True)[:max_examples]
    bank_path.write_text(json.dumps(top, indent=2))
    print(f"  Few-shot bank: {len(top)} examples")


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
