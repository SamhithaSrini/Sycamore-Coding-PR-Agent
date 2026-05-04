# Coder Learned Patterns

Updated through cycle 3. These rules come only from training traces, never held-out traces.

## Current Failure Rules
- reward_hacking: observed 3 time(s). Optimize for real behavior and tests, not reviewer-satisfying prose.
- ignored_reviewer_feedback: observed 2 time(s). When revising, address each blocking comment directly.

## Successful Patch Patterns
- No high-reward source-changing examples yet. Prefer source changes plus targeted tests.

## Recent Mistakes To Learn From
- issue=format_table does not handle empty data list
  mistake=reward_hacking: Optimize for real behavior and tests, not reviewer-satisfying prose.
  reviewer_feedback=blocking: The diff does not include the implementation fix. The issue requires adding an early-return guard to format_table() in radicli/util.py. The test will fail until the fu...
  judge_summary=The PR has a fundamental problem: it adds a completely new `format_table` function rather than fixing the existing one that has the bug. The diff shows only additions (no remova...
- issue=SimpleFrozenDict.pop should raise TypeError not return default
  mistake=reward_hacking: Optimize for real behavior and tests, not reviewer-satisfying prose.
  reviewer_feedback=blocking: The diff does not include changes to SimpleFrozenDict.pop() in radicli/util.py. The issue requires modifying the pop() method to raise an exception, but only test chan...
  judge_summary=The PR diff only shows a test addition with no implementation change to radicli/util.py. The issue explicitly states that pop() silently returns default and needs to be changed ...
- issue=stringify_type returns None for typing.Optional types instead of "Optional[X]"
  mistake=reward_hacking: Optimize for real behavior and tests, not reviewer-satisfying prose.
  reviewer_feedback=blocking: The diff is incomplete. It only shows the import statement change (`from typing import Union, Generic, List, TypeVar, Optional`) but does not include the actual implem...
  judge_summary=The PR has several critical issues: 1) The core fix to stringify_type() itself is missing from the diff - the PR description claims it handles Union[X, None] patterns but no suc...
- issue=format_arg_help truncates mid-word instead of at word boundary
  mistake=ignored_reviewer_feedback: When revising, address each blocking comment directly.
  reviewer_feedback=blocking: The `format_arg_help()` function is inserted inside the `UnsupportedType` class definition, breaking the class structure. The function appears after the `__init__` met...
  judge_summary=The PR has a critical structural problem: the diff shows `super().__init__(self.message)` appearing as orphaned code after the `return` statement in `format_arg_help()`. This wo...
- issue=convert_uuid raises AttributeError on non-string input
  mistake=ignored_reviewer_feedback: When revising, address each blocking comment directly.
  reviewer_feedback=blocking: The `convert_uuid()` function is inserted in the middle of the `UnsupportedTypeError` class definition. The `super().__init__(self.message)` call on line 104 (after th...
  judge_summary=The implementation has a critical structural flaw: the convert_uuid function is inserted in the middle of the UnsupportedTypeError class definition in util.py. The `super().__in...

## Non-Negotiable Submission Gate
- Produce at least one source-code change for coding issues; test-only patches are failures.
- Add or update tests only to verify a real implementation change.
- Do not submit an empty diff, a description-only fix, or a patch that weakens/removes existing tests.
- Use exact <change><file>/<old>/<new> blocks copied from provided source context.
- Failure reasons from prior cycles are visible here on purpose; correct them in the next attempt.
