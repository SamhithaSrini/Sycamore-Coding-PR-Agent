"""
Lean4 Formal Verifier (Anthropic SDK)

Graceful fallback: if lean binary not found, returns verified=None and continues.
Uses claude-sonnet-4-6 to generate Lean4 proof files (needs the more capable model).
"""

import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Optional
import anthropic

LEAN_BINARY = os.getenv("LEAN_BINARY", "lean")
LEAN_TIMEOUT = 30

_client = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic()
    return _client


def verify_with_lean(diff: str, lean_propositions: list) -> dict:
    if not lean_propositions:
        return {"verified": None, "coverage": 0.0, "passed": 0, "total": 0}
    if not _lean_available():
        print("  Lean4: binary not found — skipping (set LEAN_BINARY env var)")
        return {"verified": None, "coverage": 0.0, "passed": 0, "total": 0}

    verifiable = [p for p in lean_propositions if p.get("verifiable")]
    if not verifiable:
        return {"verified": None, "coverage": 0.0, "passed": 0, "total": 0}

    passed = 0
    for prop in verifiable:
        lean_code = _build_lean_file(prop, diff)
        if lean_code and _run_lean(lean_code):
            passed += 1
            print(f"  Lean4: verified '{prop.get('function_name', '?')}'")
        else:
            print(f"  Lean4: could not verify '{prop.get('function_name', '?')}'")

    total = len(verifiable)
    return {
        "verified": (passed == total) if total > 0 else None,
        "coverage": passed / total if total > 0 else 0.0,
        "passed": passed,
        "total": total,
    }


def _lean_available() -> bool:
    try:
        result = subprocess.run([LEAN_BINARY, "--version"], capture_output=True, timeout=10)
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _build_lean_file(proposition: dict, diff: str) -> Optional[str]:
    function_code = _extract_function_from_diff(diff, proposition.get("function_name", ""))
    if not function_code:
        return None
    try:
        response = _get_client().messages.create(
            model="claude-sonnet-4-6",  # Needs stronger model for Lean4 synthesis
            max_tokens=1024,
            messages=[{"role": "user", "content": f"""Given this Python function:
```python
{function_code}
```

And this proposition: {proposition['proposition']}

Write a COMPLETE, MINIMAL, SELF-CONTAINED Lean4 file that:
1. Defines an equivalent Lean4 function
2. States the proposition as a theorem
3. Proves it using omega, simp, ring, decide, or norm_num

Output ONLY valid Lean4 code. No markdown, no explanation."""}],
            temperature=0.0,
        )
        return response.content[0].text
    except Exception as e:
        print(f"  Lean4: generation failed: {e}")
        return None


def _run_lean(lean_code: str) -> bool:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".lean", delete=False) as f:
        f.write(lean_code)
        lean_file = f.name
    try:
        result = subprocess.run([LEAN_BINARY, lean_file], capture_output=True, timeout=LEAN_TIMEOUT)
        stdout = result.stdout.decode("utf-8", errors="ignore").lower()
        stderr = result.stderr.decode("utf-8", errors="ignore").lower()
        return result.returncode == 0 and "error" not in stdout and "error" not in stderr
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False
    finally:
        try:
            os.unlink(lean_file)
        except Exception:
            pass


def _extract_function_from_diff(diff: str, function_name: str) -> str:
    if not function_name:
        return ""
    lines = diff.split("\n")
    in_function, result = False, []
    for line in lines:
        if line.startswith("+") and re.search(rf"def {re.escape(function_name)}\b", line):
            in_function = True
        if in_function:
            if line.startswith("+"):
                result.append(line[1:])
            elif line.startswith("-"):
                continue
            else:
                if result and not line.startswith(" "):
                    break
    return "\n".join(result)
