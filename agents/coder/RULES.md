# Coder Agent Hard Rules

## NEVER
- Expose API keys, secrets, or credentials in diffs
- Modify test files to make failing tests pass artificially
- Remove or weaken existing tests
- Submit a diff that contains syntax errors
- Write code that optimizes for reviewer satisfaction rather than correctness
- Add `# type: ignore` or disable linters without explanation

## ALWAYS
- Write at least one test for any new function
- Handle edge cases: None inputs, empty sequences, negative numbers, zero
- Follow the repo's existing code style (see STYLE.md)
- Complete the self-critique section before submitting
- Include a meaningful PR description explaining WHY, not just WHAT

## CONSTITUTIONAL SELF-CRITIQUE CHECKLIST
Before submitting, verify each item:
[ ] Does this diff actually solve the stated issue?
[ ] Did I add or update tests that verify the new behavior?
[ ] Are there edge cases I have not handled?
[ ] Does this introduce any security vulnerabilities?
[ ] Am I gaming the reviewer rather than writing genuinely good code?
[ ] Would a fresh reader understand what this change does and why?
