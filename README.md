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

AgentHub currently has a single-session UI built on the accepted session
architecture:

- It launches one OpenCode process in a fullscreen embedded terminal.
- It represents that runtime with `AgentSession` and coordinates it through
  `SessionManager`.
- It focuses the terminal automatically.
- It forwards native keyboard and mouse interaction to the child process.
- It adapts mouse-wheel events to OpenCode's transcript-scroll shortcuts.
- It exits when Ctrl+Q is pressed or when the child process exits.

It does not yet provide:

- multiple sessions;
- a session sidebar;
- session switching, stopping, restarting, or removal;
- persisted session metadata;
- harness-native conversation resumption.

The phrase "session hub" describes the product direction, not the complete
feature set of the current prototype.

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

- `bittty`
- `textual`
- `textual-tty`

Development dependencies:

- `pytest`
- `pytest-asyncio`
- `ruff`
- `textual-dev`

Packaging uses Hatchling with an explicit `src/agenthub` wheel package.

## License

No license file is currently present. Add one before distributing the project
under an explicit open-source or proprietary license.
