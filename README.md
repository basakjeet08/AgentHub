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
- It lets the user reconcile a selected fresh runtime with a discovered,
  unloaded conversation from the same harness and working directory via Alt+M.
  Linking adopts the native ID and title without restarting the existing
  terminal.
- It provides a session sidebar for switching between managed sessions.
- It groups Agent rows under counted, display-only `LOADED` and `UNLOADED`
  headings, keeping attached runtimes above discovered conversations while
  preserving the existing session order within each group in one continuous
  navigation order. A secondary-accent bar marks the active session independently
  from the sidebar cursor, and long option labels stay on one line with an
  ellipsis.
- It keeps `AGENTS` and `SHELLS` sidebar groups visible at all times, allocating
  more space to agent conversations with a 70/30 split.
- It opens a registry-driven harness picker and working-directory browser with
  Ctrl+N, then launches the selected coding agent in the chosen directory after
  both steps are confirmed. Fresh runtimes use the temporary label `New session`
  until explicitly linked; AgentHub does not assign provider-native titles. The
  directory browser hides dot-prefixed folders by default and toggles them with
  Ctrl+H; typing filters the current directory's immediate child folders by
  name.
- It creates Fish shell sessions with Ctrl+Shift+S with an optional session name.
- When a native-backed agent exits, it unloads the runtime and reconciles only
  that harness so conversations deleted in the native CLI do not leave stale
  rows. Unidentified agents and shells retain their existing exit behavior.
- With the AGENTS list focused, Ctrl+D confirms and permanently deletes a
  highlighted native-backed conversation when its provider supports deletion.
  The logical row is removed only after native deletion is verified; unsupported
  providers show guidance without stopping a running terminal.
- It keeps hidden terminals mounted, running, and buffering output while focus
  follows the visible terminal.
- It starts Unlocked for immediate navigation and lets the user transfer all
  non-toggle shortcuts to the active terminal by locking with Ctrl+G.
- It adapts mouse-wheel events to OpenCode's transcript-scroll shortcuts and
  retains styled main-view scrollback for Antigravity, Codex, Devin, and Fish,
  while delegating alternate-screen interaction to each native TUI.

## Supported Coding-Agent Harnesses

- 🛸 Antigravity (`agy`)
- 🌀 Codex (`codex`)
- 🤖 Devin (`devin`)
- 💻 OpenCode (`opencode`)

The picker lists harnesses supported by AgentHub even when their executables are
not installed. Each native CLI owns its authentication and first-run setup.

## Current Limitations

AgentHub does not yet provide:

- a complete shortcuts dialog;
- generic user-initiated stopping or restarting of sessions;
- persisted session metadata;
- creation or renaming of native harness conversations;
- non-interactive Antigravity conversation deletion (the native CLI currently
  exposes deletion only through its interactive conversation picker).

Normal startup begins native-session discovery and may populate the agent
sidebar without starting any child process. Ctrl+N launches a fresh native CLI
runtime with no known native session ID. If later discovery finds the native
conversation, it is kept as a separate native-backed row rather than guessed to
belong to the unidentified runtime. Select the fresh running row and press Alt+M
to choose an unloaded native conversation from the same harness and working
directory. AgentHub keeps the terminal running, transfers the chosen native
identity and title onto the fresh row, and removes the duplicate discovered row.
Shell sessions continue to use AgentHub's current working directory and do not
participate in native discovery or linking.

When the `AGENTS` list owns focus, Alt+M targets its highlighted row without
requiring Enter first. Otherwise it targets the currently active Agent. Linking
a highlighted hidden runtime does not activate it or replace the terminal that
is currently visible. If the `SHELLS` list owns focus, linking is rejected
instead of falling back to an unrelated active Agent.

## Keyboard Ownership

AgentHub starts Unlocked. Ctrl+G explicitly transfers keyboard ownership:

```text
○ Unlocked  AgentHub navigation bindings are active (default)
● Locked    Ctrl+G unlocks AgentHub; every other key reaches the terminal
```

Unlocked bindings are:

```text
Ctrl+G                Lock AgentHub
Ctrl+N                Create a new agent session
Ctrl+Shift+S          New shell session
Ctrl+Shift+R          Re-sync native sessions
Alt+M                 Link highlighted or active fresh agent
Ctrl+D                Delete highlighted native-backed agent
Ctrl+P                Command Palette
Ctrl+Q                Quit
Ctrl+A, 1...9, Enter  Navigate / open agent
Ctrl+S, ↑↓, Enter     Navigate / open shell
```

Ctrl+P opens a searchable command palette for New Agent, New Shell, Refresh
Native Sessions, Open Session, Quit AgentHub, and Shortcuts. Open Session
presents running Agents, unloaded native Agents, and running Shells in one
picker. Its search matches harness names and session titles, while each result
shows only the harness icon and title with an icon legend below the list. The
other entries invoke the same application action as their corresponding
keyboard shortcut.

Home has no terminal to protect, so these application shortcuts work there
without requiring an unlock. In the sidebar, `Ctrl+A` focuses agents and `1` through `9`
moves the highlight cursor to the nth agent, while `Enter` switches to it. `Ctrl+S`
focuses shells for arrow-key navigation, while numeric keys are ignored. `Ctrl+Shift+S`
prompts for an optional shell name and creates a shell.

Ctrl+D is owned by AgentHub only while the AGENTS list has focus. With terminal
focus it continues to reach the hosted native CLI unchanged. Fresh Agents show
a warning because they have no provider-native conversation to delete; shells
do not participate in native deletion. Antigravity shows native-picker guidance
without opening confirmation or changing its current runtime.

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
- Fish available on `PATH` for shell sessions

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
