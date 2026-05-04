"""
Coding Agent (Anthropic SDK)

Context injected at inference time:
  - SKILLS.md, RULES.md, STYLE.md, CONSTITUTION.md  (firmware)
  - Top-3 high-scoring examples from few_shot_bank.json
  - Recent reviewer patterns from traces  (OA direction #2)
  - Actual relevant file content from the repo  ← fixes corrupt patches
"""

import json
import os
import re
import subprocess
from pathlib import Path
import anthropic

AGENT_DIR = Path("agents/coder")
TRACES_DIR = Path("data/traces")
REPO_PATH = Path(os.getenv("REPO_PATH", "/tmp/click"))

_client = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic()
    return _client


def _call(system: str, user: str, model: str, temperature: float = 0.2) -> str:
    response = _get_client().messages.create(
        model=model,
        max_tokens=4096,
        system=system,
        messages=[{"role": "user", "content": user}],
        temperature=temperature,
    )
    return response.content[0].text


def fetch_relevant_files(issue: dict, max_files: int = 2, context_lines: int = 60) -> str:
    """
    Grep the repo for files relevant to the issue and return the section
    around the match (not just first N lines). This gives the coder correct
    line numbers and context so `git apply` succeeds.
    """
    repo = Path(os.getenv("REPO_PATH", "/tmp/click"))
    if not repo.exists():
        return ""

    text = f"{issue.get('title', '')} {issue.get('body', '')}"

    # Prefer CamelCase identifiers and snake_case function names — avoid common words
    camel = re.findall(r'\b[A-Z][a-z]+[A-Z][A-Za-z0-9]+\b', text)   # CamelCase
    snake = re.findall(r'\b[a-z][a-z0-9_]{4,}\b', text)              # snake_case (5+ chars)
    # Rank: CamelCase first (most specific), then long snake_case
    COMMON = {"should", "would", "could", "their", "there", "where", "these", "those",
              "which", "while", "after", "before", "about", "param", "value", "error",
              "when", "with", "that", "this", "from", "have", "will", "report"}
    candidates = list(dict.fromkeys(
        [t for t in camel if t not in COMMON] +
        [t for t in snake if t not in COMMON and len(t) > 6]
    ))[:6]

    file_matches: dict = {}  # rel_path → first matching line number

    for term in candidates:
        try:
            result = subprocess.run(
                ["grep", "-rn", term, "src/", "tests/"],
                cwd=repo, capture_output=True, text=True, timeout=5
            )
            for match_line in result.stdout.splitlines():
                parts = match_line.split(":", 2)
                if len(parts) >= 2 and parts[0].endswith(".py"):
                    rel_path = parts[0]
                    try:
                        lineno = int(parts[1])
                    except ValueError:
                        lineno = 1
                    if rel_path not in file_matches:
                        file_matches[rel_path] = lineno
        except Exception:
            pass
        if len(file_matches) >= max_files:
            break

    # Fallback to types.py + core.py if nothing found
    if not file_matches:
        for fallback in ["src/click/types.py", "src/click/core.py"]:
            if (repo / fallback).exists():
                file_matches[fallback] = 1

    sections = []
    for rel_path, first_line in list(file_matches.items())[:max_files]:
        full_path = repo / rel_path
        if not full_path.exists():
            continue
        all_lines = full_path.read_text(errors="ignore").splitlines()
        # Show the window around the first match (so line numbers are accurate)
        start = max(0, first_line - 10)
        end = min(len(all_lines), first_line + context_lines)
        snippet = "\n".join(
            f"{i+1}: {l}" for i, l in enumerate(all_lines[start:end], start=start)
        )
        sections.append(
            f"### {rel_path} (lines {start+1}–{end}, line numbers shown)\n```python\n{snippet}\n```\n"
            f"NOTE: use the line numbers above in your diff hunk headers."
        )

    return "\n\n".join(sections) if sections else ""


def load_coder_context() -> dict:
    return {
        "skills": _read(AGENT_DIR / "SKILLS.md"),
        "rules": _read(AGENT_DIR / "RULES.md"),
        "style": _read(AGENT_DIR / "STYLE.md"),
        "constitution": _read(AGENT_DIR / "CONSTITUTION.md"),
        "few_shot": _load_few_shot_bank(top_k=3),
        "reviewer_patterns": _load_recent_reviewer_patterns(),
    }


def _read(path: Path) -> str:
    return path.read_text() if path.exists() else ""


def _load_few_shot_bank(top_k: int = 3) -> str:
    bank_path = AGENT_DIR / "few_shot_bank.json"
    if not bank_path.exists():
        return "No examples yet."
    bank = json.loads(bank_path.read_text())
    top = sorted(bank, key=lambda x: x.get("judge_score", 0), reverse=True)[:top_k]
    if not top:
        return "No examples yet."
    parts = []
    for i, ex in enumerate(top):
        parts.append(
            f"### Example {i+1} (score: {ex.get('judge_score', 0):.2f})\n"
            f"Issue: {ex['issue'][:200]}...\n"
            f"```diff\n{ex['diff'][:600]}\n```"
        )
    return "\n\n".join(parts)


def _load_recent_reviewer_patterns(n_traces: int = 15) -> str:
    """OA direction #2: coder sees reviewer traces at inference time."""
    if not TRACES_DIR.exists():
        return "No reviewer traces available yet."
    trace_files = sorted(TRACES_DIR.glob("*.json"), key=lambda f: f.stat().st_mtime, reverse=True)[:n_traces]
    blocking, suggestions = [], []
    for tf in trace_files:
        try:
            data = json.loads(tf.read_text())
            for review in data.get("review_attempts", []):
                for c in review.get("comments", []):
                    if c.get("severity") == "blocking":
                        blocking.append(c["content"][:150])
                    elif c.get("severity") == "suggestion":
                        suggestions.append(c["content"][:150])
        except Exception:
            continue
    if not blocking and not suggestions:
        return "No reviewer patterns observed yet."
    blocking = list(dict.fromkeys(blocking))[:5]
    suggestions = list(dict.fromkeys(suggestions))[:3]
    lines = ["Recent reviewer feedback patterns (anticipate these):"]
    if blocking:
        lines.append("\nBlocking issues the reviewer has flagged:")
        lines.extend(f"  - {p}" for p in blocking)
    if suggestions:
        lines.append("\nSuggestions the reviewer frequently makes:")
        lines.extend(f"  - {p}" for p in suggestions)
    return "\n".join(lines)


def build_coder_system_prompt(context: dict) -> str:
    template = _read(AGENT_DIR / "prompt_template.txt") or _default_prompt_template()
    return template.format(
        skills=context["skills"],
        rules=context["rules"],
        style=context["style"],
        constitution=context["constitution"],
        few_shot_examples=context["few_shot"],
        reviewer_patterns=context["reviewer_patterns"],
    )


def generate_pr(
    issue: dict,
    review_feedback: str = None,
    previous_diff: str = None,
    model: str = None,
) -> dict:
    """
    Ask the LLM for old/new code blocks, then compute the diff ourselves
    with difflib. This avoids the classic LLM failure of wrong @@ hunk counts.
    """
    context = load_coder_context()
    system_prompt = build_coder_system_prompt(context)
    model = model or os.getenv("CODER_MODEL", "claude-haiku-4-5-20251001")

    file_context = fetch_relevant_files(issue)
    file_section = (
        f"\n\n## Relevant source files (line numbers shown — use them exactly)\n{file_context}"
        if file_context else ""
    )

    change_format = """
Output format — use these XML tags:
<self_critique>your constitutional self-check</self_critique>
<change>
  <file>src/click/types.py</file>
  <old>exact original lines to replace (copy verbatim from source above)</old>
  <new>replacement lines</new>
</change>
<description>what and why</description>

Rules:
- <old> must be a verbatim copy of lines from the source files shown above
- Make the smallest change that fixes the issue
- You MUST produce a code change — even a minimal one
- If multiple changes needed, use multiple <change> blocks"""

    if review_feedback and previous_diff:
        user_content = f"""Issue: {issue['title']}

{issue['body']}{file_section}

Your previous attempt produced this diff:
```diff
{previous_diff}
```

Review feedback:
{review_feedback}
{change_format}

Produce an improved fix addressing all feedback."""
    else:
        user_content = f"""Issue: {issue['title']}

{issue['body']}{file_section}
{change_format}

Produce a fix for this issue."""

    raw = _call(system_prompt, user_content, model, temperature=0.2)
    return _parse_coder_response(raw, issue)


def _parse_coder_response(content: str, issue: dict = None) -> dict:
    self_critique = _extract_tag(content, "self_critique")
    description = _extract_tag(content, "description")

    # Build a real diff from <change> blocks using difflib
    diff = _build_diff_from_changes(content, issue)

    # Fallback: if LLM still produced a raw diff block, use it
    if not diff:
        diff = _extract_tag(content, "diff")
    if not diff:
        m = re.search(r"```diff\n(.*?)```", content, re.DOTALL)
        if m:
            diff = m.group(1).strip()

    return {
        "diff": diff,
        "description": description,
        "self_critique": self_critique,
        "raw": content,
    }


def _build_diff_from_changes(content: str, issue: dict = None) -> str:
    """
    Extract <change> blocks and build a proper unified diff using difflib.
    This guarantees correct hunk headers regardless of LLM line-counting errors.
    """
    import difflib

    repo = Path(os.getenv("REPO_PATH", "/tmp/click"))
    changes = re.findall(
        r"<change>(.*?)</change>", content, re.DOTALL
    )
    if not changes:
        return ""

    all_diff_parts = []
    for change_block in changes:
        file_path = _extract_tag(change_block, "file").strip()
        old_text = _extract_tag(change_block, "old")
        new_text = _extract_tag(change_block, "new")

        if not file_path or not old_text:
            continue

        full_path = repo / file_path
        if not full_path.exists():
            # Try common prefixes
            for prefix in ["src/", ""]:
                alt = repo / prefix / file_path
                if alt.exists():
                    full_path = alt
                    file_path = str(prefix) + file_path
                    break
            else:
                continue

        actual_content = full_path.read_text(errors="ignore")

        # Find old_text in actual file (strip leading/trailing whitespace for matching)
        old_clean = old_text.strip()
        if old_clean not in actual_content:
            # Try ignoring leading indentation differences
            old_lines = [l.strip() for l in old_clean.splitlines()]
            found = False
            for i, line in enumerate(actual_content.splitlines()):
                if line.strip() == old_lines[0]:
                    # Check if subsequent lines match
                    block = actual_content.splitlines()[i:i+len(old_lines)]
                    if [l.strip() for l in block] == old_lines:
                        old_clean = "\n".join(actual_content.splitlines()[i:i+len(old_lines)])
                        found = True
                        break
            if not found:
                continue

        new_content = actual_content.replace(old_clean, new_text.strip(), 1)
        if new_content == actual_content:
            continue

        diff_lines = list(difflib.unified_diff(
            actual_content.splitlines(keepends=True),
            new_content.splitlines(keepends=True),
            fromfile=f"a/{file_path}",
            tofile=f"b/{file_path}",
        ))
        if diff_lines:
            all_diff_parts.append("".join(diff_lines))

    return "\n".join(all_diff_parts)


def _extract_tag(text: str, tag: str) -> str:
    match = re.search(rf"<{tag}>(.*?)</{tag}>", text, re.DOTALL)
    return match.group(1).strip() if match else ""


def _default_prompt_template() -> str:
    return """You are an expert software engineer working on the click repository.

## Your Skills
{skills}

## Hard Rules (NEVER violate)
{rules}

## Code Style Guide
{style}

## Self-Critique Constitution
{constitution}

## Successful PR Examples
{few_shot_examples}

## Recent Reviewer Patterns (anticipate these to avoid rework)
{reviewer_patterns}

Always structure your response with:
<self_critique>Your constitutional self-check</self_critique>
<diff>The complete git diff using EXACT lines from source files</diff>
<description>PR description explaining what and why</description>"""
