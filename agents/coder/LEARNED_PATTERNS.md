# Coder Learned Patterns

Updated through cycle 2. These rules come only from training traces, never held-out traces.

## Current Failure Rules
- empty_diff: observed 11 time(s). Always include concrete source changes; a description is not a PR.
- reward_hacking: observed 2 time(s). Optimize for real behavior and tests, not reviewer-satisfying prose.
- low_quality: observed 1 time(s). Reproduce the failure, make the smallest source change, and verify with tests.

## Successful Patch Patterns
- No high-reward source-changing examples yet. Prefer source changes plus targeted tests.

## Recent Mistakes To Learn From
- issue=[maintenance] Lint `import typing as t`
  mistake=empty_diff: Always include concrete source changes; a description is not a PR.
  reviewer_feedback=blocking: The diff is empty. No code changes are visible for review. Please provide the actual diff showing what changes were made to implement the `import typing as t` linting....
  judge_summary=The PR diff is completely empty — there are no code changes whatsoever. The issue asks about adding a flake8 plugin (flake8-typing-as-t) to lint for 'import typing as t' usage, ...
- issue=Flush stdin after writing to a pager
  mistake=empty_diff: Always include concrete source changes; a description is not a PR.
  reviewer_feedback=blocking: The diff is empty. The PR description correctly identifies that `pager_cmd.stdin.flush()` should be added after line 468 in `src/click/_termui_impl.py` to fix the buff...
  judge_summary=The PR diff is completely empty - there is no actual code change. The description correctly identifies the problem (buffered writes to pager stdin) and the solution (adding flus...
- issue=With invoke_without_command set commands are not marked as optional
  mistake=empty_diff: Always include concrete source changes; a description is not a PR.
  reviewer_feedback=blocking: The diff only stores `self.invoke_without_command = invoke_without_command` but does not modify the code that generates the usage string. The issue requires changing h...
  judge_summary=The PR diff is completely empty - there are no code changes whatsoever. The PR description is also empty. This means no implementation was provided to address the issue. The iss...
- issue=Add support for partial shell completion options like in Path
  mistake=empty_diff: Always include concrete source changes; a description is not a PR.
  reviewer_feedback=blocking: The diff is empty. No implementation code has been provided. The issue requests adding support for partial shell completion options (similar to Path completion), but t...
  judge_summary=The PR diff is completely empty - there is no code change whatsoever. The PR description is also empty. This means no implementation was provided, no tests were written, and the...
- issue=With invoke_without_command set commands are not marked as optional
  mistake=empty_diff: Always include concrete source changes; a description is not a PR.
  reviewer_feedback=blocking: The diff only shows deletion of `test_invoked_subcommand` (lines 279-298) but does not show the implementation changes to the Click library that would fix the issue. T...
  judge_summary=The PR diff is completely empty - there are no code changes whatsoever. The PR description claims to implement a fix for marking subcommands as optional in help text when invoke...
- issue=`pyright --verifytypes` reports incomplete coverage
  mistake=reward_hacking: Optimize for real behavior and tests, not reviewer-satisfying prose.
  reviewer_feedback=blocking: Indentation is broken. The comment `# Set missing default for flags...` has been dedented to column 0, and the following `if` statement has inconsistent indentation (a...
  judge_summary=The PR description claims to fix three issues (get_help_option return type, Option.type annotation, Option.default annotation), but the actual diff only contains ONE change: con...
  touched_source=src/click/core.py

## Non-Negotiable Submission Gate
- Produce at least one source-code change for coding issues; test-only patches are failures.
- Add or update tests only to verify a real implementation change.
- Do not submit an empty diff, a description-only fix, or a patch that weakens/removes existing tests.
- Use exact <change><file>/<old>/<new> blocks copied from provided source context.
- Failure reasons from prior cycles are visible here on purpose; correct them in the next attempt.
