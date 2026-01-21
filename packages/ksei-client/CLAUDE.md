# Claude Code Preferences

## Running Python Scripts
Always use `uv run` instead of `python` to run Python scripts to ensure dependencies are properly managed.

Example:
```bash
uv run script.py
```

## Other Commands
Use `uv add` to install dependencies:
```bash
uv add package_name