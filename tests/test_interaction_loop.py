"""
Integration smoke tests for the interaction loop.
These use real API calls — run with a valid ANTHROPIC_API_KEY.
Set SKIP_API_TESTS=1 to skip tests requiring API calls.
"""

import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

SKIP_API = os.getenv("SKIP_API_TESTS", "0") == "1"

from hooks.post_pr import run_pre_review_checks
from learning.alignment import compute_alignment, aggregate_alignment_scores
from learning.trace_collector import ReviewComment


def test_pre_review_checks_detects_security_issue():
    diff = """--- a/test.py
+++ b/test.py
@@ -1,3 +1,3 @@
 def process(user_input):
-    return user_input
+    return eval(user_input)
"""
    result = run_pre_review_checks(diff)
    assert result["linter_passed"] is False
    assert any("eval" in i["message"] for i in result["issues"])


def test_pre_review_checks_passes_clean_diff():
    diff = """--- a/src/click/utils.py
+++ b/src/click/utils.py
@@ -10,3 +10,7 @@
 def my_func(x):
-    return x
+    if x is None:
+        return 0
+    return x
"""
    result = run_pre_review_checks(diff)
    assert result["linter_passed"] is True


def test_aggregate_alignment_scores():
    assert aggregate_alignment_scores([]) == (None, "single_round")
    assert aggregate_alignment_scores([None]) == (None, "single_round")
    avg, interp = aggregate_alignment_scores([0.9, 0.8])
    assert avg == pytest.approx(0.85)
    assert interp == "high"
    avg, interp = aggregate_alignment_scores([0.2, 0.3])
    assert avg == pytest.approx(0.25)
    assert interp == "low"


def test_alignment_no_comments():
    result = compute_alignment([], "some diff")
    assert result["score"] is None
    assert result["interpretation"] == "no_comments"


@pytest.mark.skipif(SKIP_API, reason="requires OpenAI API")
def test_alignment_with_addressed_comment():
    """Real API call: check that alignment detects an addressed comment."""
    from dotenv import load_dotenv
    load_dotenv()

    comments = [
        ReviewComment(
            content="Add a check for None input to avoid AttributeError",
            severity="blocking",
            category="correctness",
            persona="correctness",
        )
    ]
    diff = """--- a/test.py
+++ b/test.py
@@ -1,3 +1,5 @@
 def process(x):
-    return x.value
+    if x is None:
+        return None
+    return x.value
"""
    result = compute_alignment(comments, diff)
    assert result["score"] is not None
    assert result["score"] > 0.5   # Should detect that the comment was addressed
