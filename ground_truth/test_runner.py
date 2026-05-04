"""
Test Runner — click edition.
Apply diff in-place, run the full click test suite (~5s), revert with git checkout.
No file copying, no scoping needed — click's full suite is fast enough to run every time.
NEVER returns raw test output to agents — only aggregated pass_rate, tests_added.
"""

import json
import os
import subprocess
import tempfile
from pathlib import Path

REPO_PATH = Path(os.getenv("REPO_PATH", "/tmp/click"))
PYTEST_TIMEOUT = 60


def run_tests(diff: str) -> dict:
    """
    Apply diff in-place, run full test suite, revert with git checkout.
    """
    if not REPO_PATH.exists():
        print(f"  Test runner: repo not found at {REPO_PATH}")
        return {"pass_rate": 0.5, "coverage_delta": 0.0, "tests_added": 0, "error": "repo_not_found"}

    try:
        baseline = _run_pytest(REPO_PATH)

        apply_ok, apply_err = _apply_diff_inplace(diff, REPO_PATH)
        if not apply_ok:
            print(f"    Patch failed: {apply_err}")
            return {"pass_rate": 0.0, "coverage_delta": 0.0, "tests_added": 0, "error": apply_err}

        try:
            result = _run_pytest(REPO_PATH)
        finally:
            subprocess.run(["git", "checkout", "."],
                           cwd=REPO_PATH, capture_output=True, timeout=15)

        print(f"    Tests: {result['total_tests']} total, pass_rate={result['pass_rate']:.2f}")
        return {
            "pass_rate": result["pass_rate"],
            "coverage_delta": 0.0,
            "tests_added": max(0, result["total_tests"] - baseline["total_tests"]),
            "error": None,
        }
    except Exception as e:
        subprocess.run(["git", "checkout", "."], cwd=REPO_PATH,
                       capture_output=True, timeout=15)
        return {"pass_rate": 0.0, "coverage_delta": 0.0, "tests_added": 0, "error": str(e)}


def _apply_diff_inplace(diff: str, repo: Path) -> tuple:
    if not diff.strip():
        return False, "empty_diff"
    with tempfile.NamedTemporaryFile(mode="w", suffix=".patch", delete=False) as f:
        f.write(diff)
        patch_file = f.name
    try:
        # Try strict apply first
        strict = subprocess.run(
            ["git", "apply", "--ignore-whitespace", patch_file],
            cwd=repo, capture_output=True, timeout=15
        )
        if strict.returncode == 0:
            return True, None

        # Fallback: fuzzy patch with up to 3 lines of context tolerance
        fuzzy = subprocess.run(
            ["patch", "--fuzz=3", "--ignore-whitespace", "-p1", "-i", patch_file],
            cwd=repo, capture_output=True, timeout=15
        )
        if fuzzy.returncode == 0:
            return True, None

        err = strict.stderr.decode()[:200]
        return False, f"patch_failed: {err}"
    except subprocess.TimeoutExpired:
        return False, "patch_timeout"
    finally:
        os.unlink(patch_file)


def _run_pytest(repo: Path) -> dict:
    report_file = Path(tempfile.mktemp(suffix="_pytest_report.json"))
    cmd = [
        "python3", "-m", "pytest",
        "tests/",
        "--tb=no", "-q",
        f"--json-report", f"--json-report-file={report_file}",
        "--timeout=15",
    ]
    try:
        subprocess.run(cmd, cwd=repo, capture_output=True, timeout=PYTEST_TIMEOUT)
    except subprocess.TimeoutExpired:
        pass

    pass_rate, total = 0.0, 0
    if report_file.exists():
        try:
            report = json.loads(report_file.read_text())
            total = report.get("summary", {}).get("total", 0)
            passed = report.get("summary", {}).get("passed", 0)
            pass_rate = passed / total if total > 0 else 0.0
        except Exception:
            pass
        finally:
            report_file.unlink(missing_ok=True)

    return {"pass_rate": pass_rate, "coverage": 0.0, "total_tests": total}
