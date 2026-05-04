# Reviewer Rubric

## What BLOCKING issues look like
- Logic errors that would produce wrong results for valid inputs
- Missing error handling for obvious failure modes (None, empty, negative)
- Security vulnerabilities (eval on user input, unsafe subprocess calls)
- Tests that don't actually test the changed behavior (trivially passing assertions)
- Regression risk: changes that would break existing tests or related functionality
- Incomplete fix: the PR addresses the example in the issue but not the root cause

## What SUGGESTIONS look like
- Performance improvements with clear, measurable benefit
- Better variable naming that aids readability
- Missing docstring on a public function
- Simpler alternative approach that reduces complexity
- Test case that would cover an additional edge case

## What NITPICKS look like
- Minor style inconsistencies
- Optional type hints
- Whitespace preferences within PEP 8 bounds

## Approval Criteria
- Approve ONLY when ALL blocking issues are resolved
- Explain your confidence score in specific terms
- If confidence < 0.7: request changes even if no blocking issues found
- If approving: write ≥3 specific sentences about why the code is correct

## Anti-Collapse Rule
A vague "looks good" is not an approval. Either find something to improve,
or write a detailed, specific justification for why nothing needs improvement.

## Cycle 1 Calibration

### Common Mistakes to Avoid

**1. Don't approve based on syntax alone—verify semantic correctness**
- When a fix involves domain-specific operations (state space systems, matrix algebra, signal processing, CLI argument parsing), ensure you understand what the operation is supposed to do, not just that it compiles.
- Matrix operation direction matters: A change from prepending to appending zeros is a logic change, not a refactor. Verify the mathematical meaning and data layout match the intended fix.
- For CLI/argument parsing changes, trace through the actual behavior: does the change produce the correct output format for the documented use case?

**2. Verify test coverage actually validates the fix**
- When a fix changes behavior, confirm that existing tests would catch a regression if the fix were reverted.
- If tests pass both before and after a behavioral change, the tests are insufficient—this is a blocking issue.
- Check whether the test assertions are trivial (e.g., just checking a string contains a substring) or actually validate the semantic correctness of the change.

**3. Understand scope and propagation rules**
- Don't assume configuration or markers defined in one file automatically propagate to all related files (e.g., `pytestmark` in `conftest.py` has specific scoping rules).
- Trace the actual execution path: where does the code run, and does the fix apply there?
- For environment-specific fixes (headless, CI, etc.), verify the condition is checked at the right point in the execution flow.

**4. When uncertain, don't approve**
- If you're unsure whether a change is correct, mark it as "?" or "request changes" rather than approving.
- Approval signals confidence that the code is correct. Uncertainty should be explicit.
- If you can't trace through the logic or don't understand the domain, that's a signal to ask clarifying questions before approving.

## Cycle 2 Calibration

### Lessons from Incorrect Approvals

**1. Trace scope and propagation explicitly—don't assume**
- **Mistake**: Approving a `pytestmark` definition in `conftest.py` without verifying it actually applies to the test files being fixed.
- **Correct approach**: Understand pytest's marker scoping rules. `pytestmark` in `conftest.py` only applies to tests in that directory and subdirectories, not to sibling test files. Verify the fix applies where the tests actually run.
- **Action**: For configuration/marker changes, explicitly trace which test files are affected and confirm the fix reaches them. Map out the directory structure and verify the scope covers all affected tests. If tests are in `tests/sa/` and the fix is in `conftest.py` at the root, the fix won't apply to those tests.

**2. Understand the semantic intent of the change, not just the syntax**
- **Mistake**: Approving a CLI usage string change without understanding what the change actually communicates to users about command optionality.
- **Correct approach**: When a fix changes output format (usage strings, error messages, data layout), verify the semantic meaning is correct. For example, `[COMMAND [ARGS]...]` vs `[COMMAND] [ARGS]...` has different meaning: the first indicates the command itself is optional, the second doesn't. Confirm the change matches the intended behavior by cross-referencing against the actual code behavior (e.g., `invoke_without_command=True`).
- **Action**: For output/format changes, read the change as a user would and verify it correctly represents the intended behavior. Trace the code to confirm the usage string matches what the code actually accepts.

**3. Don't approve if you can't explain the fix in domain terms**
- **Mistake**: Approving changes in unfamiliar domains (pytest mechanics, CLI conventions, error handling) without fully understanding them.
- **Correct approach**: If you don't understand the domain well enough to explain why the fix is correct, request clarification or mark as uncertain rather than approving. For error handling changes, understand what exception is being caught and why the new approach is better (e.g., catching `ValueError` and using `str(e)` instead of `str(value)` gives users the actual error message, not the input value).
- **Action**: Before approving, write out in your own words what the fix does and why it solves the problem. If you can't do this clearly, don't approve.

**4. Verify the fix is complete and reaches all affected code paths**
- **Mistake**: Approving a fix that solves the stated problem but doesn't address the root cause or all related code paths.
- **Correct approach**: Trace through the codebase to identify all places where the issue could manifest. Confirm the fix applies to all of them, not just the example in the issue. For error handling, verify that the exception type being caught is the right one and that removing related exception types (e.g., `UnicodeError`) is justified by the Python version or context.
- **Action**: Search for related code patterns and verify the fix is applied consistently across the codebase. Identify the exact location where the bug manifests and confirm the fix reaches that point. Check if related exception handlers should also be updated.

## Cycle 3 Calibration

### Critical Lessons from Continued Mistakes

**1. File location and scope rules are not optional—verify them explicitly**
- **Mistake**: Approving a `pytestmark` definition in `conftest.py` at the root level, assuming it applies to all test files in the project, when it actually only applies to tests in that directory and subdirectories.
- **Correct approach**: Understand that `pytestmark` in `conftest.py` has directory-scoped application. If test files that need the marker are in sibling directories or different branches of the tree, the marker won't reach them. Explicitly check the file structure and trace which tests are actually affected.
- **Action**: Before approving any configuration/marker change, draw out or mentally map the directory structure. Verify that the file containing the fix is in a location where its scope covers all the tests that need it. If tests are in `tests/sa/` and the fix is in `conftest.py` at the root, the fix won't apply to those tests. This is a blocking issue.

**2. Semantic correctness requires understanding the user-facing contract**
- **Mistake**: Approving a CLI usage string change that syntactically looks correct but changes the semantic meaning of what the command accepts, without verifying this matches the actual code behavior.
- **Correct approach**: When a fix changes user-facing output (usage strings, error messages, data formats), verify that the change accurately reflects what the code actually does. Bracket notation in CLI usage has specific meaning: `[COMMAND [ARGS]...]` means the command is optional; `[COMMAND] [ARGS]...` means the command is required but args are optional. Confirm the usage string matches the actual parameter configuration (e.g., `invoke_without_command=True` should produce the first form).
- **Action**: For any user-facing output change, read the change from the user's perspective. Cross-reference it against the actual code behavior. If they don't match, it's a blocking issue. Verify the code parameter that controls this behavior and confirm the usage string reflects it.

**3. Don't approve based on "looks reasonable"—verify the fix actually solves the stated problem**
- **Mistake**: Approving a change because it appears to address the issue in the PR description, without actually tracing through the code to confirm the fix reaches the problem site.
- **Correct approach**: Identify the