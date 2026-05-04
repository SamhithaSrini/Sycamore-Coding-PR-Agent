# Reviewer Calibration Notes

## Systematic Corrections

These are cases where the reviewer was wrong relative to ground truth.
Use these to avoid repeating the same mistakes.

## Initial Calibration

- Do not approve code just because it matches the style of the issue description.
- A PR that handles only the specific example in the issue is not complete.
- Tests that only test the happy path are insufficient.
- Security issues in helper functions matter even if the main function looks clean.

## Distributional Shift Warning

As the coder improves over training cycles, the reviewer will see higher-quality PRs.
Keep standards anchored to tests, judge scores, and issue requirements rather than the
historical distribution of coder submissions.

## Current Auto-Calibration Summary

- Repeated low-alignment failures indicate blocking feedback must be concrete and easy to act on.
- Repeated adversarial-strictness warnings indicate the reviewer should approve genuinely correct, well-tested PRs.
- When uncertain, explain the uncertainty and request targeted evidence instead of broad rewrites.

## Cycle 3 Auto-Calibration

- 2 trace(s): low alignment and bad outcome — coder likely ignored valid feedback; reviewer should make blocking changes explicit.

## Cycle 1 Auto-Calibration

- 2 trace(s): low alignment and bad outcome — coder likely ignored valid feedback; reviewer should make blocking changes explicit.

## AUTO-RECALIBRATION

Adversarial reviewer: 100% rejection rate. Be willing to approve good PRs.
