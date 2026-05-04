"""
Post-PR hook: runs linter + static analysis on the diff before the reviewer sees it.
The reviewer DOES see linter results, but NOT test results (those stay in ground_truth/).
"""

import re
import subprocess
import tempfile
import os


def run_pre_review_checks(diff: str) -> dict:
    """
    Quick static checks on the diff. Returns results for reviewer context injection.
    """
    issues = []

    # 1. Check for obvious security issues in diff
    security_issues = _scan_for_security_issues(diff)
    issues.extend(security_issues)

    # 2. Check for syntax errors in added Python lines
    syntax_issues = _check_python_syntax(diff)
    issues.extend(syntax_issues)

    # 3. Check for common anti-patterns
    antipattern_issues = _check_antipatterns(diff)
    issues.extend(antipattern_issues)

    linter_passed = len([i for i in issues if i.get("severity") == "error"]) == 0

    return {
        "linter_passed": linter_passed,
        "issues": issues,
    }


def _scan_for_security_issues(diff: str) -> list:
    issues = []
    added_lines = [line[1:] for line in diff.split("\n") if line.startswith("+") and not line.startswith("+++")]

    PATTERNS = [
        (r"os\.system\(", "error", "os.system() is a security risk — use subprocess with shell=False"),
        (r"eval\(", "error", "eval() is a security risk"),
        (r"exec\(", "warning", "exec() can be dangerous"),
        (r"(?:password|secret|api_key|token)\s*=\s*['\"][^'\"]+['\"]", "error", "Potential hardcoded credential"),
        (r"__import__\(", "warning", "Dynamic import detected"),
    ]

    for i, line in enumerate(added_lines):
        for pattern, severity, message in PATTERNS:
            if re.search(pattern, line, re.IGNORECASE):
                issues.append({"line": i, "severity": severity, "message": message})

    return issues


def _check_python_syntax(diff: str) -> list:
    """Extract added Python lines and check syntax."""
    added_lines = []
    for line in diff.split("\n"):
        if line.startswith("+") and not line.startswith("+++"):
            added_lines.append(line[1:])

    if not added_lines:
        return []

    code = "\n".join(added_lines)
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(code)
        tmp = f.name

    try:
        result = subprocess.run(
            ["python", "-m", "py_compile", tmp],
            capture_output=True, timeout=10
        )
        if result.returncode != 0:
            err = result.stderr.decode()[:200]
            return [{"line": None, "severity": "error", "message": f"Syntax error: {err}"}]
    except Exception:
        pass
    finally:
        try:
            os.unlink(tmp)
        except Exception:
            pass

    return []


def _check_antipatterns(diff: str) -> list:
    issues = []
    added_lines = [line[1:] for line in diff.split("\n") if line.startswith("+") and not line.startswith("+++")]

    ANTIPATTERNS = [
        (r"except:\s*$", "warning", "Bare except clause — use except Exception"),
        (r"pass\s*$", "warning", "Empty except/function body"),
        (r"print\(", "warning", "print() in production code — consider logging"),
        (r"TODO|FIXME|HACK|XXX", "warning", "TODO/FIXME left in code"),
    ]

    for i, line in enumerate(added_lines):
        for pattern, severity, message in ANTIPATTERNS:
            if re.search(pattern, line):
                issues.append({"line": i, "severity": severity, "message": message})

    return issues
