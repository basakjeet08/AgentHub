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

- It starts on a lightweight Home screen with essential shortcuts, discovers
  native conversations in the background, and does not launch a coding-agent
  process until one is selected.
- It provides a persistent session sidebar, Home content area, and application
  status bar.
- It uses Textual's built-in Tokyo Night theme with shared semantic component
  styles.
- It represents logical native conversations with `AgentSession`, keeps their
  terminal runtime optional, and coordinates them through `SessionManager`.
- It keeps provider activity separate from runtime lifecycle through a
  provider-neutral `AgentActivity` model and reducer. Loaded Agents show
  Unknown, Idle, Working, Needs Input, or Done in the sidebar; Antigravity,
  Codex, Devin, and OpenCode drive the states their structured provider events
  support.
- On Linux, it sends a system notification with the desktop theme sound when
  any loaded Agent newly enters Needs Input or Done, including the Agent
  currently open while AgentHub is focused. Repeated events in the same state
  are ignored.
- It launches each terminal child in its session's normalized working directory
  without changing AgentHub's own directory or using a shell command.
- It discovers Codex, OpenCode, Devin, and Antigravity sessions through
  provider-specific adapters and displays them as unloaded sidebar entries.
- It resumes an unloaded conversation by its exact native ID on selection,
  mounts the resulting terminal, and reuses that runtime on later selections.
- It re-syncs native conversations in place with Ctrl+Shift+R while preserving
  running terminals and reconciling unloaded sidebar entries.
- It lets the user reconcile the active fresh runtime with a discovered,
  unloaded conversation from the same harness and working directory through
  the command palette. Linking adopts the native ID and title without
  restarting the existing terminal.
- It provides a session sidebar for switching between managed sessions.
- It presents `LOADED`, `UNLOADED`, and `SHELLS` as counted sidebar tabs, with
  one category occupying the session area at a time. A secondary-accent bar
  marks the active session independently from the sidebar cursor, and long
  option labels stay on one line with an ellipsis.
- Its New Agent palette command opens a registry-driven harness picker and
  working-directory browser, then launches the selected coding agent after both
  steps are confirmed. Fresh runtimes use the temporary label `New session`
  until explicitly linked; AgentHub does not assign provider-native titles. The
  directory browser hides dot-prefixed folders by default and toggles them with
  Ctrl+H; typing filters the current directory's immediate child folders by name.
- Its New Shell palette command creates Fish shell sessions with an optional name.
- When a native-backed agent exits, it unloads the runtime and reconciles only
  that harness so conversations deleted in the native CLI do not leave stale
  rows. Unidentified agents and shells retain their existing exit behavior.
- Its contextual Delete palette command operates on the active native-backed
  Agent. The logical row is removed only after native deletion is verified;
  unsupported providers show guidance without stopping a running terminal.
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

Codex activity hooks require the normal Codex trust review. On the first Codex
launch after this feature is installed, open `/hooks`, inspect and trust the
AgentHub activity hooks. Until trusted, Codex continues normally and the sidebar
remains at its initial `Idle` state instead of receiving live updates. AgentHub
does not bypass hook trust.

Antigravity activity uses a named observer in its shared
`~/.gemini/config/hooks.json`. AgentHub installs or refreshes only its own named
entry and preserves every existing hook. The observer is correlated by the
child-only AgentHub environment, returns Antigravity's neutral responses, and
does not report activity when Antigravity is launched outside AgentHub.

## Current Limitations

AgentHub does not yet provide:

- a complete shortcuts dialog;
- generic user-initiated stopping or restarting of sessions;
- persisted session metadata;
- a reliable Antigravity `Needs Input` signal; its passive hooks report Idle,
  Working, and Done without inferring permission or question prompts;
- desktop activity notifications on macOS;
- a provider lifecycle signal for approval resolution; AgentHub observes Codex
  approval-decision keys to clear `Needs Input`, while Devin can retain it until
  the tool finishes, and another approval hook may still resolve a request
  without AgentHub observing that resolution;
- creation or renaming of native harness conversations;
- non-interactive Antigravity conversation deletion (the native CLI currently
  exposes deletion only through its interactive conversation picker).

Normal startup begins native-session discovery and may populate the agent
sidebar without starting any child process. New Agent launches a fresh native
CLI runtime with no known native session ID. If later discovery finds the native
conversation, it is kept as a separate native-backed row rather than guessed to
belong to the unidentified runtime. Open the fresh running row, then choose its
contextual Link command to select an unloaded native conversation from the same
harness and working directory. AgentHub keeps the terminal running, transfers
the chosen native identity and title onto the fresh row, and removes the
duplicate discovered row. Shell sessions continue to use AgentHub's current
working directory and do not participate in native discovery or linking.

## Getting Started

AgentHub is a terminal workspace for managing coding-agent conversations and
shell sessions from one place. It embeds each supported coding agent's native
terminal interface rather than replacing it.

### Session categories

- **Loaded** — Agent sessions currently running and ready to use.
- **Unloaded** — Existing agent conversations available to resume.
- **Shells** — Regular Fish shell terminals running inside AgentHub.

### Quick start

```text
New Agent  Ctrl+P → New Agent → Choose Coding Agent → Choose Directory
New Shell  Ctrl+P → New Shell → Optionally Enter a Name
```

To create an Agent, open the Command Palette with `Ctrl+P`, choose **New
Agent**, select the coding agent, and select its working directory. The new
runtime uses the temporary label `New session` until it is explicitly linked
to a discovered provider conversation.

To create a shell, open the Command Palette, choose **New Shell**, and enter an
optional name. Shell sessions use Fish and AgentHub's current working directory.

## Navigation Basics

### Command Palette

- `Ctrl+P` opens the Command Palette.
- Start typing to filter the available actions.
- Use `↑` and `↓` to move through results.
- Press `Enter` to run the highlighted action.

Common actions include New Agent, New Shell, Open Session, Refresh Native
Sessions, and Quit AgentHub. Link and Delete appear only when they apply to the
Agent currently open in the main terminal. **Open Session** presents loaded
Agents, unloaded Agents, and Shells in one searchable picker; its search matches
coding-agent names and session titles.

### Sidebar navigation

- `Ctrl+S` focuses the sidebar without changing its selected tab or cursor.
- `←` and `→` switch between Loaded, Unloaded, and Shells.
- `↑` and `↓` move through sessions in the selected tab.
- `Enter` opens the selected session or resumes an unloaded Agent.

## Session Management

### Create a session

Use `Ctrl+P` and select **New Agent** or **New Shell**. See the Quick Start
flows under [Getting Started](#getting-started).

### Resume an existing Agent

Resume an unloaded Agent and continue its existing conversation:

```text
Ctrl+S → Unloaded → Choose Session → Enter
```

You can also choose **Open Session** from the Command Palette and search for the
conversation.

### Link a fresh Agent

Link connects a newly created AgentHub session to its matching saved provider
conversation without restarting its terminal. The fresh Agent must be open in
the main terminal, and only unloaded conversations from the same coding agent
and working directory are offered.

```text
Open Fresh Agent → Ctrl+P → Link → Choose Conversation
```

### Refresh sessions

Press `Ctrl+Shift+R` to scan supported coding agents for new, changed, or
removed conversations. Running terminals remain attached while unloaded rows
are reconciled with provider state.

### Delete an Agent

Delete permanently removes the currently open provider conversation where the
provider supports non-interactive deletion. The Agent must be open in the main
terminal.

```text
Open Agent → Ctrl+P → Delete
```

Providers without deletion support, such as Antigravity, show guidance instead
of stopping the runtime or opening a confirmation.

> **Important:** Link and Delete apply to the Agent currently open in the main
> terminal, not the session merely highlighted in the sidebar. Press `Enter` to
> open a highlighted Agent before invoking either action.

## Controls & Shortcuts

### Keyboard ownership

AgentHub starts Unlocked. `Ctrl+G` explicitly transfers keyboard ownership:

```text
○ Unlocked  AgentHub navigation shortcuts are active (default)
● Locked    Ctrl+G unlocks AgentHub; every other key reaches the terminal
```

Home has no terminal to protect, so AgentHub shortcuts work there without
requiring an unlock. With a terminal active, locking AgentHub sends every key
except `Ctrl+G` to the native terminal. `Ctrl+G` remains AgentHub's ownership
toggle even when a hosted CLI also uses that key.

### Global shortcuts

```text
Ctrl+P                Command Palette
Ctrl+S                Focus Sidebar
Ctrl+G                Lock / unlock AgentHub
Ctrl+Shift+R          Refresh native sessions
```

### Sidebar controls

```text
← / →                 Change sidebar tab
↑ / ↓                 Navigate sessions
Enter                 Open / resume
```

New Agent, New Shell, Link, Delete, and Quit are palette-only operations. Their
former shortcuts are not intercepted by AgentHub and reach a focused terminal
unchanged. `Ctrl+A` and `Tab` likewise remain native terminal input. AgentHub
does not rewrite a native CLI's other bindings.

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
