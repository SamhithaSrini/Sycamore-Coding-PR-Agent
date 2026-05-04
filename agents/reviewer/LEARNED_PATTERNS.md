# Reviewer Learned Patterns

Updated through cycle 2. Use these as calibration memory, not as replacements for the rubric.

## Grounded Calibration
- Ground-truth confirmed review decisions: 18.
- Ground-truth contradicted review decisions/comments: 6.
- Watch for: The code change itself is correct and straightforward - removing the deprecated (1 case(s)).
- Watch for: The fix is correct and minimal: adding `pager_cmd.stdin.flush()` after each writ (1 case(s)).
- Watch for: The fix is minimal, correct, and directly addresses the issue. The change from ` (1 case(s)).
- Watch for: The fix correctly addresses the issue by passing the ValueError message to self. (1 case(s)).
- Watch for: The core fix is correct: passing str(e) instead of str(value) to self.fail() giv (1 case(s)).
- Watch for: The fix correctly addresses the issue: when `invoke_without_command=True`, the u (1 case(s)).

## Persona Debate Lessons
- correct_decision=approve; right_personas=architecture; wrong_personas=correctness, security

## Review Gate
- Request changes for empty diffs, test-only patches, removed tests, or descriptions without implementation.
- Approve only when the diff changes the relevant source behavior and tests meaningfully verify it.
- If personas disagree, prefer the persona whose decision matches tests/judge-grounded outcomes in recent traces.
