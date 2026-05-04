# Reviewer Learned Patterns

Updated through cycle 3. Use these as calibration memory, not as replacements for the rubric.

## Grounded Calibration
- Ground-truth confirmed review decisions: 12.
- Ground-truth contradicted review decisions/comments: 3.
- Watch for: The core fix is correct: adding len(p) >= 2 prevents single-character quote stri (1 case(s)).
- Watch for: The join_strings() function implementation is correct - it properly filters None (1 case(s)).
- Watch for: low_alignment_with_good_outcome: reviewer comments were not actionable (1 case(s)).

## Persona Debate Lessons
- correct_decision=approve; right_personas=correctness; wrong_personas=security, architecture
- correct_decision=request_changes; right_personas=correctness, architecture; wrong_personas=security

## Review Gate
- Request changes for empty diffs, test-only patches, removed tests, or descriptions without implementation.
- Approve only when the diff changes the relevant source behavior and tests meaningfully verify it.
- If personas disagree, prefer the persona whose decision matches tests/judge-grounded outcomes in recent traces.
