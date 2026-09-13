# AgentHub

AgentHub is a Textual-based TUI for managing multiple terminal-native
coding-agent sessions from one application.

> Manage multiple native coding-agent terminal sessions from one TUI.

AgentHub does **not** reimplement a coding agent's interface. OpenCode, Codex,
Claude Code, Devin CLI, and similar tools continue to run their native terminal
UIs inside an embedded terminal powered by `textual-tty` and `bittty`.

For the accepted design, lifecycle constraints, validation work, and
implementation direction, read **[ARCHITECTURE.md](ARCHITECTURE.md)** before
making structural changes.

## Project Status

AgentHub currently has a minimal multi-session runtime built on the accepted
session architecture:

- It launches one OpenCode process by default in an embedded terminal.
- It represents that runtime with `AgentSession` and coordinates it through
  `SessionManager`.
- It mounts every session known at application composition time and displays
  the active one through a `ContentSwitcher`.
- It provides a session sidebar and temporary Ctrl+1/Ctrl+2 switching.
- It keeps hidden terminals mounted, running, and buffering output while focus
  follows the visible terminal.
- It forwards native keyboard and mouse interaction to the child process.
- It adapts mouse-wheel events to OpenCode's transcript-scroll shortcuts.
- It exits when Ctrl+Q is pressed, and preserves the original exit-on-child
  behavior when only one session exists.

It does not yet provide:

- a user-facing New Session flow;
- launching a session in a directory different from AgentHub's own current
  directory;
- stopping, restarting, or removing sessions;
- persisted session metadata;
- harness-native conversation resumption.

The runtime supports multiple pre-created sessions, but the normal application
startup still creates only one until the New Session workflow is implemented.

## Architecture

AgentHub manages native coding-agent processes through embedded terminal
sessions:

```text
AgentHubApp → SessionManager → AgentSession → AgentTerminal → textual-tty/Bitty
```

See [ARCHITECTURE.md](ARCHITECTURE.md) for the complete design, ownership model,
lifecycle constraints, and implementation roadmap.

## Requirements

- Python 3.13 or newer
- A pyenv environment named `agenthub` (selected by `.python-version`)

The environment used during initial development was created with Python
3.13.15:

```bash
pyenv virtualenv 3.13.15 agenthub
```

## Install

Install AgentHub and its development dependencies:

```bash
python -m pip install -e ".[dev]"
direnv allow
```

Verify the installation:

```bash
python -c "import agenthub; print('ok')"
ruff check src/ tests/
python -m pytest
agenthub
```

## Run

```bash
agenthub
```

The command is registered in `pyproject.toml` as:

```toml
[project.scripts]
agenthub = "agenthub.main:main"
```

## Project Structure

See [Repository Structure](ARCHITECTURE.md#repository-structure) for the
authoritative package tree and module responsibilities.

## Dependencies

Runtime dependencies declared in `pyproject.toml`:

- `bittty==0.1.4`
- `textual==8.2.8`
- `textual-tty==0.4.0`

Development dependencies:

- `pytest`
- `pytest-asyncio`
- `ruff`
- `textual-dev`

Packaging uses Hatchling with an explicit `src/agenthub` wheel package.

## License

No license file is currently present. Add one before distributing the project
under an explicit open-source or proprietary license.
