# AgentHub

A TUI hub for managing coding-agent sessions.

## Requires

- Python >= 3.13
- pyenv environment `agenthub` (see `.python-version`)

## Install

```fish
python -m pip install -e ".[dev]"
```

## Run

```fish
agenthub
```

or

```fish
python -m agenthub
```

## Structure

```text
src/agenthub/
  main.py        # thin entry: construct + run the app
  app.py         # AgentHubApp: layout, bindings, orchestration
  terminal/      # AgentTerminal widget adapter
```
