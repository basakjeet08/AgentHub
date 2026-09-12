# AgentHub

A TUI hub for managing coding-agent sessions.

## Requires

- Python >= 3.13
- pyenv environment `agenthub` (see `.python-version`)

## Setup

First time only — create the environment:

```fish
pyenv virtualenv 3.13.15 agenthub
```

Then install (run again whenever dependencies change):

```fish
python -m pip install -e ".[dev]"
direnv allow
```

Verify:

```fish
python -c "import agenthub; print('ok')"
ruff check src/
agenthub
```

## Run

```fish
agenthub
```

## Structure

```text
src/agenthub/
  main.py        # thin entry: construct + run the app
  app.py         # AgentHubApp: layout, bindings, orchestration
  terminal/      # AgentTerminal widget adapter + harness selection
```
