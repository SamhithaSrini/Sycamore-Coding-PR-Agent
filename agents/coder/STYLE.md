# click Code Style Guide

## Python Style
- PEP 8, 88-char line limit (black-formatted)
- Type hints on all public functions
- f-strings preferred over .format() or %

## click Conventions
- Commands are functions decorated with @click.command() or @click.group()
- Options use @click.option(), arguments use @click.argument()
- Use click.echo() not print() for output
- ctx.ensure_object(dict) for passing context between commands
- Errors: raise click.UsageError("message") or click.BadParameter()
- Testing: use click.testing.CliRunner() — never patch sys.argv directly

## Testing
- Tests live in tests/ at the repo root
- Use CliRunner().invoke(cmd, args) to test commands
- Check result.exit_code == 0 and result.output
- Test both success and error paths

## Diff Style
- One logical change per diff
- No unrelated whitespace changes
- Include test file changes alongside source changes
