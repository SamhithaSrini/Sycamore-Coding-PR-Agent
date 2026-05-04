"""
Fine-Tuning Pipeline

Anthropic does not provide a public fine-tuning API, so this module:
  - Generates the JSONL training datasets (same format, useful for analysis/future use)
  - Skips the API submission step
  - Still updates env vars if a custom model ID is manually configured

The improvement mechanism works through firmware updates (SKILLS.md, RUBRIC.md,
CALIBRATION.md, few-shot bank) which are the primary learning signal here.
"""

import json
import os
from pathlib import Path
from typing import List


def build_coder_finetune_dataset(signals: dict) -> List[dict]:
    system_prompt = _read("agents/coder/prompt_template.txt")
    examples = []

    for ex in signals.get("coder_positive", []):
        if not ex.get("diff"):
            continue
        examples.append({
            "messages": [
                {"role": "user", "content": f"Issue: {ex.get('issue_title', '')}\n\n{ex['issue']}\n\nGenerate a PR to fix this issue."},
                {"role": "assistant", "content": (
                    f"<self_critique>This approach directly addresses the issue.</self_critique>\n"
                    f"<diff>\n{ex['diff']}\n</diff>\n"
                    f"<description>\n{ex.get('description', 'Fix for the reported issue.')}\n</description>"
                )},
            ]
        })

    # Revision examples from multi-round traces
    traces_dir = Path("data/traces")
    if traces_dir.exists():
        for trace_path in sorted(traces_dir.glob("*.json"))[:50]:
            try:
                t = json.loads(trace_path.read_text())
                cb = t.get("confidence", {})
                if (t.get("total_rounds", 1) > 1
                        and cb.get("use_for_training")
                        and len(t.get("pr_attempts", [])) >= 2
                        and len(t.get("review_attempts", [])) >= 1):
                    examples.append({
                        "messages": [
                            {"role": "user", "content": _build_revision_prompt(
                                issue=t.get("issue_body", ""),
                                first_diff=t["pr_attempts"][0]["diff"],
                                review_comments=t["review_attempts"][0].get("comments", []),
                            )},
                            {"role": "assistant", "content": f"<diff>\n{t['pr_attempts'][1]['diff']}\n</diff>"},
                        ]
                    })
            except Exception:
                continue

    return examples


def build_reviewer_finetune_dataset(signals: dict) -> List[dict]:
    examples = []

    for ex in signals.get("reviewer_positive", []):
        if not ex.get("pr_diff"):
            continue
        examples.append({
            "messages": [
                {"role": "user", "content": f"Review this PR:\n```diff\n{ex['pr_diff'][:3000]}\n```"},
                {"role": "assistant", "content": json.dumps({
                    "decision": ex.get("decision", "approve"),
                    "comments": ex.get("comments", [])[:10],
                    "confidence": 0.9,
                })},
            ]
        })

    for ex in signals.get("reviewer_negative", []):
        if not ex.get("pr_diff"):
            continue
        gt_decision = "approve" if ex.get("gt_assessment") == "good" else "request_changes"
        examples.append({
            "messages": [
                {"role": "user", "content": f"Review this PR:\n```diff\n{ex['pr_diff'][:3000]}\n```"},
                {"role": "assistant", "content": json.dumps({
                    "decision": gt_decision,
                    "comments": [],
                    "confidence": 0.75,
                    "calibration_note": (
                        f"GT: '{ex.get('gt_assessment', '?')}'. "
                        f"Reason: {ex.get('reason', ex.get('judge_reasoning', ''))[:200]}"
                    ),
                })},
            ]
        })

    return examples


def run_finetune_cycle(training_cycle: int):
    """
    Generate JSONL datasets. Actual fine-tuning submission is skipped
    (Anthropic doesn't have a public fine-tuning API).
    Primary improvement mechanism is firmware updates (SKILLS.md, RUBRIC.md, few-shot bank).
    """
    from learning.signal_extractor import load_all_traces, extract_training_signals

    print(f"\n  Fine-tuning cycle {training_cycle}")
    traces = load_all_traces()
    signals = extract_training_signals(traces)

    min_examples = int(os.getenv("MIN_POSITIVE_EXAMPLES_FOR_FINETUNE", "5"))
    if len(signals["coder_positive"]) < min_examples:
        print(f"  Not enough positive examples ({len(signals['coder_positive'])} < {min_examples}). Skipping.")
        return None

    coder_examples = build_coder_finetune_dataset(signals)
    reviewer_examples = build_reviewer_finetune_dataset(signals)

    Path("data/finetune_datasets").mkdir(parents=True, exist_ok=True)
    coder_path = Path(f"data/finetune_datasets/coder_cycle{training_cycle}.jsonl")
    reviewer_path = Path(f"data/finetune_datasets/reviewer_cycle{training_cycle}.jsonl")

    _write_jsonl(coder_path, coder_examples)
    _write_jsonl(reviewer_path, reviewer_examples)
    print(f"  Coder dataset:    {len(coder_examples)} examples → {coder_path}")
    print(f"  Reviewer dataset: {len(reviewer_examples)} examples → {reviewer_path}")
    print(f"  (Anthropic fine-tuning API not public — datasets saved for future use)")

    return {"coder_model": None, "reviewer_model": None}


def _write_jsonl(path: Path, examples: List[dict]):
    with open(path, "w") as f:
        for ex in examples:
            f.write(json.dumps(ex) + "\n")


def _read(path_str: str) -> str:
    p = Path(path_str)
    return p.read_text() if p.exists() else ""


def _build_revision_prompt(issue: str, first_diff: str, review_comments: list) -> str:
    comments_str = "\n".join(
        f"- [{c.get('severity', '?')}] {c.get('content', '')}"
        for c in review_comments[:5]
    )
    return f"""Issue:
{issue}

Your previous PR:
```diff
{first_diff[:2000]}
```

Review feedback:
{comments_str}

Generate an improved PR addressing all feedback."""
