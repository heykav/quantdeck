# Contributing

Thanks for looking. Bug reports, fixes and documentation improvements are welcome.

1. Open an issue first for anything bigger than a small fix, so we can agree on the approach.
2. Fork, make a branch, and keep the change small and focused.
3. Add or update a test that fails before your change and passes after.
4. Run the same checks as CI before opening the pull request:

```bash
ruff check .
ruff format --check src tests examples scripts
mypy
pytest --cov=quantdeck --cov-report=term-missing
```

5. In the pull request, say what changed and how you checked it.

By contributing you agree your work is released under the repository's licence. Please follow the [code of conduct](CODE_OF_CONDUCT.md).
