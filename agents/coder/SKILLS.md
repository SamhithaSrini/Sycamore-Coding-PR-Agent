# Coder Agent Skills

## Core Capabilities
- Implement Python bug fixes with proper error handling
- Write pytest tests using click.testing.CliRunner
- Follow click's coding conventions (see STYLE.md)
- Produce clean, minimal diffs that touch only necessary lines
- Write descriptive PR descriptions explaining motivation

## click-Specific Knowledge
- click.option() and click.argument() for CLI parameters
- click.Context and ctx.obj for sharing state between commands
- click.echo() for output, click.style() for colors
- click.testing.CliRunner for testing — always use this, never patch sys.argv
- click.BadParameter, click.UsageError for user-facing errors
- @click.pass_context and @click.pass_obj for context management
- multi-command groups: @click.group() with subcommands

## Diff Format
- Produce unified diff format compatible with `git apply`
- Include `--- a/` and `+++ b/` headers
- Include the test change alongside the source change

## Quality Signals
- High-reward PRs: minimal changes, clear tests with CliRunner, correct edge cases
- Low-reward PRs: broad sweeping changes, missing tests, wrong logic

## Cycle 1 Updates

### Critical Warnings
- **Avoid low-quality submissions**: 33 consecutive low_quality failures indicate systematic approach failure
- Do not submit PRs without comprehensive test coverage
- Do not refactor unrelated code in the same PR as bug fixes
- Verify logic correctness before submission — edge cases matter
- **Zero high-quality outcomes in multi-round traces**: Current strategy is fundamentally misaligned

### Actionable Patterns
- **Before any code**: Read problem statement twice, identify exact failure mode, reproduce locally
- **Test-first discipline**: Write failing test on original code, verify it fails, then implement fix
- **Minimal scope**: Fix only the identified bug — no refactoring, no "while I'm here" changes
- **Validation gate**: Run full test suite locally, confirm all tests pass before submission
- **PR clarity**: Explicitly state: (1) what bug exists, (2) why it happens, (3) how the fix addresses it
- Keep PRs laser-focused: one bug fix = one minimal diff
- Always include both positive and negative test cases
- Test error paths and boundary conditions explicitly
- Validate assumptions about input/output before coding
- Do not guess at requirements — ask or infer from existing test patterns only

## Cycle 2 Updates

### Critical Warnings
- **Persistent low-quality pattern**: 38 consecutive low_quality failures across cycle 2 indicates fundamental misalignment
- **Multi-round failure**: 0 high-quality outcomes in multi-round traces — do not iterate on rejected PRs without root cause analysis
- **Submission discipline**: Each submission must pass local validation before sending; do not rely on reviewer feedback to catch basic errors

### Actionable Patterns
- **Root cause first**: Before coding, explicitly identify: (1) what the bug is, (2) where in the code it occurs, (3) why the current code fails
- **Local validation mandatory**: Run the exact test case that fails on original code, confirm reproduction, then verify fix resolves it
- **No multi-round iteration**: If a PR is rejected, analyze why before resubmitting — do not submit similar fixes hoping for different results
- **Test coverage non-negotiable**: Every code path touched by the fix must have explicit test coverage; missing tests = automatic low quality
- **Scope discipline**: Fix the identified bug only — zero tolerance for refactoring, style changes, or unrelated improvements in the same PR
- **Edge case validation**: Explicitly test boundary conditions, error states, and invalid inputs relevant to the bug
- **PR description precision**: State the exact failure mode, root cause, and how the fix prevents recurrence — vague descriptions correlate with rejection

## Cycle 3 Updates

### Critical Warnings
- **Systemic failure across all cycles**: 44 consecutive low_quality failures with 0 high-quality outcomes in multi-round traces indicates fundamental approach breakdown
- **Submission strategy is broken**: Current methodology produces only rejections; incremental iteration on failed PRs does not work
- **Do not continue current pattern**: Resubmitting similar fixes or iterating on rejected PRs will not improve outcomes

### Actionable Patterns
- **Complete restart required**: Analyze a single successful PR from the codebase (if available) and reverse-engineer its structure, test patterns, and scope
- **Hypothesis-driven approach**: Before touching code, write down: (1) exact failure symptom, (2) minimal test case that reproduces it, (3) predicted fix location
- **Validation before submission**: Run the failing test on original code, apply fix, run all tests, verify no regressions — this must pass 100% locally
- **Scope verification**: Count lines changed in diff; if >50 lines or >3 files, scope is too broad — split into separate PRs
- **Test-first non-negotiable**: Write test that fails on original code first; if test passes on original code, the bug hypothesis is wrong
- **PR description checklist**: Include (1) exact error message or failure mode, (2) root cause analysis with code line references, (3) how fix prevents recurrence, (4) test coverage summary
- **No multi-round submissions**: Do not resubmit a rejected PR without explicit evidence that the root cause of rejection has been addressed
- **Assume zero context**: Write PR descriptions as if reviewer has never seen the codebase; be explicit about every assumption