"""
Bootstrap Script — click edition

1. Clones pallets/click to REPO_PATH
2. Fetches real GitHub issues from pallets/click
3. Splits into training and held-out sets
4. Extracts RLHF preference pairs from git history

Usage:
  python scripts/bootstrap_repo.py
"""

import json
import os
import subprocess
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
import requests
from dotenv import load_dotenv
load_dotenv(override=True)

REPO_URL = "https://github.com/pallets/click.git"
GITHUB_REPO = "pallets/click"
REPO_PATH = Path(os.getenv("REPO_PATH", "/tmp/click"))
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
ISSUES_PATH = Path("data/issues")
HELD_OUT_PATH = Path("data/held_out")


def clone_click():
    if REPO_PATH.exists() and (REPO_PATH / ".git").exists():
        print(f"click already cloned at {REPO_PATH}, pulling latest...")
        subprocess.run(["git", "pull", "--ff-only"], cwd=REPO_PATH, capture_output=True)
    else:
        print(f"Cloning click to {REPO_PATH}...")
        subprocess.run(
            ["git", "clone", "--depth=200", REPO_URL, str(REPO_PATH)],
            check=True
        )
    print(f"  click ready at {REPO_PATH}")


def fetch_click_issues(n_training: int = 20, n_held_out: int = 5) -> tuple:
    """Fetch open bug issues from pallets/click."""
    headers = {"Authorization": f"token {GITHUB_TOKEN}"} if GITHUB_TOKEN else {}
    issues = []
    page = 1

    print("Fetching click issues from GitHub...")
    while len(issues) < n_training + n_held_out + 10:
        url = (
            f"https://api.github.com/repos/{GITHUB_REPO}/issues"
            f"?state=open&per_page=50&page={page}&sort=created&direction=desc"
        )
        resp = requests.get(url, headers=headers, timeout=30)
        if resp.status_code == 403:
            print("  GitHub rate limit hit. Set GITHUB_TOKEN for higher limits.")
            break
        if resp.status_code != 200:
            print(f"  GitHub API error: {resp.status_code}")
            break
        batch = resp.json()
        if not batch:
            break
        for issue in batch:
            if issue.get("pull_request"):
                continue
            body = issue.get("body", "") or ""
            if len(body) < 50:
                continue
            # Skip documentation/design/workflow issues — coder can't produce valid diffs
            title_lower = issue["title"].lower()
            skip_keywords = ["tutorial", "screenshot", "glossary", "document", "wip:", "design",
                             "roadmap", "add screenshot", "introduction to", "high level"]
            if any(kw in title_lower for kw in skip_keywords):
                continue
            issues.append({
                "id": str(issue["number"]),
                "title": issue["title"],
                "body": body[:3000],
                "labels": [l["name"] for l in issue.get("labels", [])],
                "url": issue["html_url"],
                "created_at": issue["created_at"],
            })
            if len(issues) >= n_training + n_held_out + 5:
                break
        page += 1
        if page > 5:
            break

    if not issues:
        print("  No issues fetched — using synthetic fallback issues")
        issues = _synthetic_click_issues(n_training + n_held_out)

    training = issues[:n_training]
    held_out = issues[n_training: n_training + n_held_out]
    print(f"  {len(training)} training issues, {len(held_out)} held-out issues")
    return training, held_out


def save_issues(issues: list, path: Path):
    path.mkdir(parents=True, exist_ok=True)
    # Clear old issues
    for f in path.glob("*.json"):
        f.unlink()
    for issue in issues:
        (path / f"issue_{issue['id']}.json").write_text(json.dumps(issue, indent=2))
    print(f"  Saved {len(issues)} issues to {path}")


def extract_git_preferences():
    if not REPO_PATH.exists():
        return
    from learning.rlhf_pipeline import extract_preference_pairs_from_git
    pairs = extract_preference_pairs_from_git(str(REPO_PATH))
    out = Path("data/preference_pairs/pairs.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(pairs, indent=2))
    print(f"  Extracted {len(pairs)} preference pairs from git history")


def _synthetic_click_issues(n: int) -> list:
    templates = [
        {
            "id": f"synth_{i}",
            "title": f"Bug: click option {i} behaves incorrectly",
            "body": (
                f"When using `@click.option('--value', type=int, default={i})` "
                f"the option does not handle edge case {i} correctly.\n\n"
                f"```python\nimport click\n@click.command()\n"
                f"@click.option('--val', default={i})\ndef cmd(val):\n    click.echo(val)\n```\n\n"
                f"Expected: correct output. Got: incorrect behavior."
            ),
            "labels": ["bug"],
            "url": f"https://github.com/pallets/click/issues/{2000+i}",
            "created_at": "2024-01-01T00:00:00Z",
        }
        for i in range(n)
    ]
    return templates


def main():
    print("=" * 60)
    print("Sycamore Bootstrap — pallets/click")
    print("=" * 60)

    clone_click()

    training_issues, held_out_issues = fetch_click_issues(n_training=20, n_held_out=5)
    save_issues(training_issues, ISSUES_PATH)
    save_issues(held_out_issues, HELD_OUT_PATH)

    # Clear old traces from sympy runs
    traces_dir = Path("data/traces")
    if traces_dir.exists():
        old = list(traces_dir.glob("*.json"))
        for f in old:
            f.unlink()
        print(f"  Cleared {len(old)} old sympy traces")

    # Clear old metrics
    metrics = Path("data/metrics_history.json")
    if metrics.exists():
        metrics.unlink()
        print("  Cleared old metrics history")

    print("\nExtracting RLHF preference pairs from click git history...")
    extract_git_preferences()

    print("\nBootstrap complete.")
    print(f"  Training issues: {ISSUES_PATH}")
    print(f"  Held-out issues: {HELD_OUT_PATH}")
    print("\nNext: python scripts/run_training_cycle.py")


if __name__ == "__main__":
    main()
