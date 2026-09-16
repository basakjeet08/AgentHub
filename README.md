# AgentHub

AgentHub is a Textual-based TUI for managing multiple terminal-native
coding-agent sessions from one application.

> Manage multiple native coding-agent terminal sessions from one TUI.

AgentHub does **not** reimplement a coding agent's interface. Supported coding
agents continue to run their native terminal UIs inside an embedded terminal
powered by `textual-tty` and `bittty`.

For the accepted design, lifecycle constraints, validation work, and
implementation direction, read **[ARCHITECTURE.md](ARCHITECTURE.md)** before
making structural changes.

## Project Status

AgentHub currently has a Home-first application shell backed by the accepted
multi-session runtime architecture:

- It starts on a neutral Home screen, discovers native conversations in the
  background, and does not launch a coding-agent process until one is selected.
- It provides a persistent session sidebar, Home content area, and application
  status bar.
- It uses Textual's built-in Tokyo Night theme with shared semantic component
  styles.
- It represents logical native conversations with `AgentSession`, keeps their
  terminal runtime optional, and coordinates them through `SessionManager`.
- It launches each terminal child in its session's normalized working directory
  without changing AgentHub's own directory or using a shell command.
- It discovers Codex, OpenCode, Devin, and Antigravity sessions through
  provider-specific adapters and displays them as unloaded sidebar entries.
- It resumes an unloaded conversation by its exact native ID on selection,
  mounts the resulting terminal, and reuses that runtime on later selections.
- It re-syncs native conversations in place with Ctrl+Shift+R while preserving
  running terminals and reconciling unloaded sidebar entries.
- It provides a session sidebar for switching between managed sessions.
- It keeps `AGENTS` and `SHELLS` sidebar groups visible at all times, allocating
  more space to agent conversations with a 70/30 split.
- It opens a registry-driven harness picker, session-name prompt, and
  working-directory browser with Ctrl+N, then launches the selected coding
  agent in the chosen directory after all three steps are confirmed. The
  directory browser hides dot-prefixed folders by default and toggles them with
  Ctrl+H; typing filters the current directory's immediate child folders by
  name.
- It lazily creates reusable Fish sessions by pressing Ctrl+S followed by a
  slot number from 1…9.
- It removes sessions whose child processes exit, releases their Fish slots,
  and returns active exits to Home without interrupting a live active sibling.
- It keeps hidden terminals mounted, running, and buffering output while focus
  follows the visible terminal.
- It starts Unlocked for immediate navigation and lets the user transfer all
  non-toggle shortcuts to the active terminal by locking with Ctrl+G.
- It adapts mouse-wheel events to OpenCode's transcript-scroll shortcuts and
  retains styled main-view scrollback for Antigravity, Codex, Devin, and Fish,
  while delegating alternate-screen interaction to each native TUI.

## Supported Coding-Agent Harnesses

- Antigravity (`agy`)
- Codex (`codex`)
- Devin (`devin`)
- OpenCode (`opencode`)

The picker lists harnesses supported by AgentHub even when their executables are
not installed. Each native CLI owns its authentication and first-run setup.

## Current Limitations

AgentHub does not yet provide:

- a complete shortcuts dialog;
- user-initiated stopping, restarting, or removal of live sessions;
- persisted session metadata;
- creation, renaming, or deletion of native harness conversations.

Normal startup begins native-session discovery and may populate the agent
sidebar without starting any child process. Ctrl+N retains the current legacy
creation flow until native creation is implemented. Fish shell slots continue
to use AgentHub's current working directory and do not participate in native
discovery.

## Keyboard Ownership

AgentHub starts Unlocked. Ctrl+G explicitly transfers keyboard ownership:

```text
○ Unlocked  AgentHub navigation bindings are active (default)
● Locked    Ctrl+G unlocks AgentHub; every other key reaches the terminal
```

Unlocked bindings are:

```text
Ctrl+G          Lock AgentHub
Ctrl+N          Create a new agent session
Ctrl+P          Command Palette
Ctrl+Q          Quit
Ctrl+A, 1...9   Select a numbered agent session
Ctrl+S, 1...9   Open or select a persistent Fish shell slot
```

Home has no terminal to protect, so these application shortcuts work there
without requiring an unlock. After Ctrl+A or Ctrl+S focuses a sidebar group,
press a plain digit from 1 through 9 to select the numbered entry. Ctrl+digit
combinations are intentionally left to the active terminal.

Ctrl+G remains AgentHub's ownership toggle even when a hosted CLI also assigns
that key. AgentHub does not rewrite the native CLI's other bindings.

## Architecture

AgentHub manages native conversations and their disposable embedded terminal
runtimes:

```text
AgentHubApp → SessionManager → AgentSession → AgentTerminal → textual-tty/Bitty
```

See [ARCHITECTURE.md](ARCHITECTURE.md) for the complete design, ownership model,
lifecycle constraints, and implementation roadmap.

## Requirements

- Python 3.13 or newer
- A pyenv environment named `agenthub` (selected by `.python-version`)
- Any desired coding-agent CLIs available on `PATH`: `agy`, `codex`, `devin`,
  and/or `opencode`
- Fish available on `PATH` for numbered shell slots

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
