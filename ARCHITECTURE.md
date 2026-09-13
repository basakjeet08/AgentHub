# AgentHub Architecture

This document is the architectural source of truth for AgentHub maintainers,
contributors, coding agents, and future design discussions. It separates
accepted boundaries from implementation hypotheses and deferred capabilities.

For installation and a concise product overview, see [README.md](README.md).

## Product Goal

AgentHub is a Textual-based terminal user interface for managing multiple
terminal-native coding-agent sessions from one application.

> Manage multiple native coding-agent terminal sessions from one TUI.

AgentHub does **not** reimplement a coding agent's interface. OpenCode, Codex,
Claude Code, Devin CLI, and similar tools continue to render and handle input in
their native terminal interfaces. AgentHub embeds those interfaces through
`textual-tty` and `bittty`, and adds session management around them.

The architecture in this document should guide future implementation work unless
experience with the real system demonstrates that a boundary needs to change.
Validated repository facts, open technical questions, and deferred ideas are
identified separately so planned behavior is not mistaken for implemented
behavior.

## Current Implementation

The current execution path is:

```text
main.py
   │
   ▼
AgentHubApp
   │
   ▼
SessionManager
   │
   ▼
AgentSession
   │
   ├── AgentHarness
   │
   └── AgentTerminal
   │
   ▼
textual-tty
   │
   ▼
bittty / PTY
   │
   ▼
OpenCode
```

### Current responsibilities

`AgentHubApp`:

- owns one `SessionManager`;
- creates one initial OpenCode session;
- mounts that session's fullscreen terminal widget;
- focuses that widget on mount;
- owns a priority Ctrl+Q application binding;
- exits when the terminal child process exits.

`SessionManager` currently:

- creates and retains sessions in creation order;
- makes a new session active;
- selects existing sessions by ID;
- constructs terminal runtimes without mounting them.

`AgentSession` currently connects an AgentHub ID and name with its intended
working directory, harness definition, and terminal runtime.

`AgentHarness` is immutable semantic data containing a stable ID, display name,
tuple command, and terminal-independent scrolling shortcuts. It does not create
widgets or import Bitty.

`AgentTerminal` currently:

- subclasses `textual_tty.Terminal`;
- consumes an `AgentHarness`;
- converts semantic key modifiers into Bitty constants;
- converts mouse-wheel movement into agent-specific transcript navigation;
- awaits Bitty reader-task and child-process cleanup during unmount;
- delegates terminal emulation and process interaction to
  `textual-tty`/`bittty`.

Only one harness is registered:

```text
registry key: opencode
command:      opencode
default:      yes
```

OpenCode's current transcript-scroll policy is:

```text
scroll down → Ctrl+Alt+E
scroll up   → Ctrl+Alt+Y
wheel step  → send the selected shortcut three times
```

When the child application has enabled terminal mouse tracking, the child owns
the wheel and `AgentTerminal` delegates to `textual-tty`. When mouse tracking is
off, `AgentTerminal` sends the configured transcript-scroll shortcuts instead.

### Current repository structure

```text
src/agenthub/
├── __init__.py
├── main.py
├── app.py
├── harnesses/
│   ├── __init__.py
│   ├── model.py
│   ├── opencode.py
│   └── registry.py
├── sessions/
│   ├── __init__.py
│   ├── model.py
│   └── manager.py
└── terminal/
    ├── __init__.py
    └── widget.py
```

The core ownership boundaries are now implemented, while the visible UI remains
single-session. Sidebar navigation and user-facing multi-session lifecycle
operations have not been added yet.

## Architecture

The accepted architecture uses two central runtime concepts:

- `AgentSession`
- `SessionManager`

The high-level architecture is:

```text
                         AgentHubApp
                    UI / DOM / navigation
                             │
                             ▼
                       SessionManager
                  session coordination/state
                             │
                     ┌───────┴────────┐
                     ▼                ▼
                AgentSession      AgentSession
                     │
                ┌────┴────┐
                ▼         ▼
          AgentHarness  AgentTerminal
                           │
                           ▼
                     textual-tty
                           │
                           ▼
                         bittty
                           │
                           ▼
                  Coding-agent process
```

The compact form is:

```text
App
 ↓
SessionManager
 ↓
AgentSession
 ├── AgentHarness
 └── AgentTerminal
          ↓
     textual-tty
          ↓
        bittty
```

### Critical ownership distinction

Python object/runtime ownership and Textual DOM ownership are different:

```text
AgentSession conceptually owns its terminal runtime.
AgentHubApp owns where and how the terminal widget is mounted and displayed.
```

`SessionManager` managing an `AgentSession` must not be interpreted as the
manager mounting or unmounting Textual widgets. The manager coordinates logical
sessions; the app controls the widget tree, layout, focus, and visibility.

## Core Concepts

### AgentHarness

`AgentHarness` is an immutable, semantic description of a supported coding
agent. It answers:

- What kind of agent is this?
- What stable ID identifies it in configuration and persistence?
- What name should the UI display?
- What command launches it?
- What terminal-specific behavior does it require?

The implemented model is:

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class KeyStroke:
    key: str
    ctrl: bool = False
    alt: bool = False
    shift: bool = False


@dataclass(frozen=True)
class ScrollKeys:
    down: KeyStroke
    up: KeyStroke
    steps: int = 3


@dataclass(frozen=True)
class AgentHarness:
    id: str
    display_name: str
    command: tuple[str, ...]
    scroll: ScrollKeys
```

OpenCode is described without importing Bitty:

```python
OPENCODE = AgentHarness(
    id="opencode",
    display_name="OpenCode",
    command=("opencode",),
    scroll=ScrollKeys(
        down=KeyStroke("e", ctrl=True, alt=True),
        up=KeyStroke("y", ctrl=True, alt=True),
    ),
)
```

The stable `id` is used by code, configuration, CLI arguments, and eventual
persistence. `display_name` is used by the UI. A tuple keeps `command` actually
immutable inside a frozen dataclass.

`AgentHarness` must not:

- construct Textual widgets;
- import `bittty` constants;
- manage sessions or application state;
- know about `AgentHubApp` or `SessionManager`;
- manage persistence;
- contain terminal-process lifecycle logic.

Conceptually:

```text
AgentHarness = immutable agent blueprint
```

### AgentTerminal

`AgentTerminal` is AgentHub's native-terminal adapter around:

```text
textual-tty
    ↓
bittty
```

It owns terminal behavior such as:

- keyboard and paste input;
- mouse input and focus behavior;
- semantic-to-Bitty key conversion;
- harness-specific transcript scrolling;
- terminal rendering;
- process output;
- terminal/process events;
- awaited reader-task and child-process cleanup;
- PTY interaction delegated to `textual-tty`/`bittty`.

The terminal currently receives the complete `AgentHarness`:

```python
class AgentTerminal(TtyTerminal):
    def __init__(
        self,
        harness: AgentHarness,
        *,
        working_directory: Path | None = None,
    ):
        ...
```

The terminal currently needs almost all of the harness's meaningful runtime
configuration. If harness metadata grows substantially in the future, a
smaller `TerminalProfile` or launch specification may become useful. Do not add
that abstraction until real code requires it.

`AgentTerminal` must not know about:

- `SessionManager`;
- the session sidebar;
- session selection;
- SQLite or persistence;
- application navigation;
- application quit policy.

It may emit a process-exit event, but the app and session coordinator decide
what that event means for AgentHub.

Conceptually:

```text
AgentTerminal = live native-terminal adapter
```

### AgentSession

`AgentSession` represents one AgentHub-managed agent runtime and its identity.
It connects:

```text
AgentHub identity
        +
working directory
        +
harness definition
        +
terminal runtime
```

The implemented model is:

```python
@dataclass
class AgentSession:
    id: str
    name: str
    cwd: Path
    harness: AgentHarness
    terminal: AgentTerminal
```

Conceptual example after arbitrary working-directory launch is supported:

```text
id:       session-1
name:     Auth Refactor
cwd:      ~/Projects/backend
harness:  OpenCode
terminal: mounted OpenCode terminal runtime
```

The session conceptually owns the terminal runtime, but `AgentHubApp` remains
responsible for mounting that widget and controlling its visibility in the
Textual DOM.

Do not add lifecycle-state enums, native harness session IDs, persistence
records, or separate runtime objects until the implementation needs them.

Conceptually:

```text
AgentSession = AgentHub identity around one agent runtime
```

### SessionManager

`SessionManager` is AgentHub's application/runtime coordinator for sessions. It
is not intended to be a pure domain service.

It coordinates:

- which sessions exist;
- which session is active;
- creation and selection;
- lookup and enumeration;
- eventually stopping, restarting, and removal once those lifecycle operations
  exist and are tested at the terminal boundary.

The implemented public behavior is:

```python
class SessionManager:
    def __init__(self) -> None:
        self._sessions: dict[str, AgentSession] = {}
        self._active_session_id: str | None = None

    def create(
        self,
        *,
        name: str,
        cwd: Path,
        harness: AgentHarness,
    ) -> AgentSession:
        ...

    def select(self, session_id: str) -> AgentSession:
        ...

    @property
    def sessions(self) -> tuple[AgentSession, ...]:
        ...

    @property
    def active_session(self) -> AgentSession | None:
        ...
```

Session IDs are generated internally, sessions are returned in creation order,
new sessions become active, and selecting an unknown ID raises `KeyError`.

Do not declare `stop()` or `restart()` complete until `AgentTerminal` exposes
explicit, reliable, tested lifecycle operations for them.

`SessionManager` must not:

- mount or unmount Textual widgets;
- manipulate CSS, `ContentSwitcher`, or DOM visibility;
- parse terminal escape sequences;
- import Bitty constants or access `bittty.Board`;
- handle mouse or keyboard events directly.

Conceptually:

```text
SessionManager = session collection and lifecycle coordinator
```

### AgentHubApp

`AgentHubApp` is the Textual application and UI orchestrator. It owns one
`SessionManager` and is responsible for:

- application startup and shutdown;
- layout and the Textual DOM;
- terminal widget mounting and visibility;
- the session sidebar and dialogs;
- application keybindings such as Ctrl+Q;
- terminal focus;
- translating UI actions into manager operations;
- displaying the active session's terminal;
- deciding how to respond when a terminal process exits.

Example interaction:

```text
User selects "Auth Refactor"
        │
        ▼
AgentHubApp
        │
        ▼
SessionManager.select(session_id)
        │
        ▼
App updates terminal visibility and focus
```

Ctrl+Q belongs at this layer:

```text
Ctrl+Q
   ↓
AgentHubApp binding
   ↓
quit AgentHub
```

It should not be implemented as `AgentTerminal` calling `self.app.exit()`.

Conceptually:

```text
AgentHubApp = Textual UI, DOM, navigation, and application policy
```

## Textual and Process Lifecycle

The most important implementation constraint discovered during exploration is
that `textual-tty` ties process lifetime to widget lifetime:

```text
Terminal.on_mount()   → starts the child PTY process
Terminal.on_unmount() → stops the child process
```

Consequently, switching sessions must not naïvely unmount the previously active
terminal if inactive sessions are expected to continue running.

The intended model is:

```text
┌─────────────────────────────────┐
│ ContentSwitcher or container    │
│                                 │
│ Terminal A   mounted, hidden    │
│ Terminal B   mounted, visible   │
│ Terminal C   mounted, hidden    │
└─────────────────────────────────┘
```

Switching should mean changing visibility and focus, not unmounting the old
terminal and mounting the new one.

An automated integration test now confirms with the installed Textual and
`textual-tty` versions that hiding a mounted terminal leaves its process alive
and that application shutdown stops all mounted terminal processes. Output
buffering and screen restoration still require validation before significant
sidebar work.

Textual dispatches convention-based event handlers across the widget class
hierarchy. `AgentTerminal` therefore prevents the automatic parent mount and
unmount handlers when it calls those handlers explicitly. This ensures each PTY
starts exactly once and allows unmounting to await Bitty's private reader task
and child-process cleanup. Keep this version-sensitive logic inside the terminal
adapter and protect it with lifecycle tests.

Multiple mounted terminals also imply resource costs: each live session owns a
child process, PTY, terminal board, scrollback, and widget. AgentHub may need to
make that cost visible eventually, but no resource-management abstraction is
needed for the first multi-session implementation.

## Process-Exit Handling

The current app exits whenever its only terminal emits `ProcessExited`. That is
acceptable for preserving one-session prototype behavior.

With multiple sessions, the desired flow becomes:

```text
AgentTerminal emits ProcessExited
        │
        ▼
AgentHubApp resolves the affected AgentSession
        │
        ▼
SessionManager updates session/runtime coordination
        │
        ├── preserve or remove the stopped session
        ├── select another session if necessary
        └── optionally quit if no sessions remain
```

The terminal should not decide to quit the entire application. The
implementation also needs a reliable mapping from the Textual message sender to
the corresponding session without making `AgentTerminal` depend on
`SessionManager`.

## Terminal Boundary and Bitty

Bitty is an implementation detail of the terminal layer. The rest of AgentHub
should see `AgentTerminal`, semantic key descriptions, and AgentHub-level
events—not:

- `bittty.Board`;
- Bitty modifier constants;
- PTY implementation details;
- terminal parser internals.

The desired dependency boundary is:

```text
Harness semantic configuration
             │
             ▼
       AgentTerminal
 semantic-to-Bitty translation
             │
             ▼
        textual-tty
             │
             ▼
           bittty
```

If the terminal implementation is ever replaced, harness definitions, session
coordination, and most application code should require minimal modification.

The implementation imports `bittty.constants` only from the terminal adapter
and declares Bitty as a direct dependency. Harness, session, manager, and app
modules remain independent of Bitty.

## Working Directories

Every useful session needs an explicit working directory:

```python
cwd: Path
```

The eventual launch behavior is:

```python
AgentTerminal(
    harness=OPENCODE,
    working_directory=Path("~/Projects/foo").expanduser(),
)
```

The installed `textual-tty.Terminal` constructor currently accepts a command
but not a working directory. AgentHub currently accepts only the application
process's working directory, records its normalized path on `AgentSession`, and
rejects a different requested launch directory with `NotImplementedError`.
This prevents session metadata from claiming a directory that the child process
did not actually inherit.

Arbitrary-directory session creation must not be exposed in the UI until the
project has identified and validated a proper `textual-tty`/Bitty extension
point.

`textual_tty.Terminal.cwd` already stores a child-reported OSC 7 path. Future
launch configuration should therefore use a distinct name such as
`working_directory` or `launch_cwd` rather than changing the meaning of that
inherited attribute.

Do not implement this as a shell string such as:

```python
command=f"cd {cwd} && opencode"
```

That would introduce shell dependence, quoting hazards, and unnecessary
coupling between launch behavior and harness configuration.

## Harness-Specific Behavior

Different agents may require different terminal behaviors. Such differences
belong in semantic harness configuration consumed by `AgentTerminal`.

Prefer:

```text
OpenCode harness
├── command
└── semantic scroll policy
```

over conditionals scattered through the application:

```python
if agent == "opencode":
    ...
elif agent == "codex":
    ...
```

Harness configuration should describe intent. Only the terminal adapter should
translate that intent into the current terminal implementation's API.

## Planned UI Relationship

The eventual UI is conceptually:

```text
┌──────────────────────┬────────────────────────────────────┐
│ Sessions             │                                    │
│                      │                                    │
│ + New Session        │                                    │
│                      │                                    │
│ > Auth Refactor      │       Active AgentTerminal         │
│   API Cleanup        │                                    │
│   Payment Bug        │                                    │
│                      │                                    │
└──────────────────────┴────────────────────────────────────┘
```

The sidebar displays and selects `AgentSession` objects. It must not operate
directly on terminal internals.

## Repository Structure

The implemented architectural domains use dedicated packages so their public
boundaries remain stable as more harnesses and session behavior are added:

```text
src/agenthub/
├── __init__.py
├── main.py              # entry point
├── app.py               # Textual application and DOM ownership
├── harnesses/
│   ├── __init__.py      # public harness API
│   ├── model.py         # immutable semantic models
│   ├── opencode.py      # OpenCode definition
│   └── registry.py      # built-in harness lookup
├── sessions/
│   ├── __init__.py      # public session API
│   ├── model.py         # AgentSession runtime model
│   └── manager.py       # session coordination
└── terminal/
    ├── __init__.py
    └── widget.py        # textual-tty/Bitty adapter
```

Packages are appropriate here because harnesses, sessions, and terminal hosting
are already distinct architectural concepts with multiple responsibilities or
expected implementations. Imports elsewhere should prefer the package public
APIs rather than reaching into `model.py`, `manager.py`, or individual harness
modules.

Do not create empty `ui/`, `persistence/`, or `config/` packages yet. Add those
when the corresponding implementation begins.

The governing rule is:

> Establish packages for real architectural domains early, but do not create
> empty placeholder layers or speculative abstractions.

## Implementation Progress and Sequence

The architectural foundation is implemented:

1. `AgentHarness` is immutable semantic data with stable identity.
2. Bitty translation is isolated inside `AgentTerminal`.
3. Ctrl+Q is an application-owned priority binding.
4. `AgentSession` and `SessionManager` represent and coordinate runtimes.
5. The app creates one managed OpenCode session while preserving the existing
   fullscreen behavior.
6. An integration test proves that two terminals remain mounted and running
   while one is hidden, focus moves to the visible terminal, and app shutdown
   terminates both processes.

The remaining sequence is:

1. Add proper working-directory launch support at the terminal dependency
   boundary.
2. Validate hidden-terminal output buffering, screen restoration, keyboard
   isolation, and process-exit routing.
3. Add the sidebar, terminal container, and session switching.
4. Add explicit terminal lifecycle operations before session stop, restart, or
   removal.
5. Add persistence and native session resumption only when the runtime model is
   stable.

## Validation Tasks

Validated with the installed dependency versions:

- Terminal A and Terminal B can remain mounted simultaneously.
- Hiding Terminal A does not unmount it or terminate its process.
- Focus can move from the hidden terminal to the visible terminal.
- App shutdown terminates all owned child processes reliably.

Still to validate before substantial multi-session UI work:

- Only the visible terminal receives user input.
- Switching visibility returns a terminal with its screen state intact.
- A hidden terminal continues receiving and buffering process output.
- Exiting one process can be mapped to the correct session.
- A process can be launched directly with the session's `cwd` without shell
  command composition.

These experiments may influence implementation details, but they do not by
themselves invalidate the ownership model.

## Testing Direction

The architectural foundation now has automated coverage for:

- immutable harness configuration and stable registry identity;
- manager invariants and active-session selection;
- behavior when selecting an unknown session;
- terminal semantic-key to Bitty translation;
- application creation with one managed session;
- explicit rejection of unsupported launch directories;
- hidden mounted terminal survival;
- focus switching between mounted terminals;
- warning-free reader-task and child-process cleanup during application
  shutdown.

Future tests should cover hidden output buffering, restored screen state,
keyboard isolation, process-exit routing, working-directory launch, and the
installed `agenthub` command.

Tests that launch processes should use a harmless controllable test command or
fake harness, not require an actual OpenCode conversation.

## Future Persistence

Persistent session metadata and a currently running terminal are different
things and should eventually be represented separately.

Possible persistent data:

```text
SessionRecord
─────────────
id
name
harness_id
cwd
native_harness_session_id
created_at
last_used
```

Possible runtime data:

```text
AgentSession / SessionRuntime
─────────────────────────────
AgentTerminal
running process
current lifecycle state
```

The principle is:

```text
persistent session ≠ currently running process
```

SQLite is likely appropriate when persistence becomes necessary. Do not add it
before the session runtime and lifecycle are proven.

## Future Harness Resume

A human-readable AgentHub session name is not sufficient to resume a native
coding-agent conversation. Resume support will eventually require:

```text
AgentHub session ID
        +
harness-native session ID
        +
working directory
```

For example:

```text
AgentHub name:     Auth Refactor
Harness session:  abc123
Project:           ~/Projects/backend
```

The harness abstraction may eventually describe how its agent creates and
resumes native sessions. This is deliberately deferred.

## Architectural Rules

Future work should preserve these rules:

1. AgentHub manages native agent UIs; it does not reimplement them.
2. `AgentHarness` is immutable semantic configuration, not a widget factory.
3. Harness IDs are stable machine identifiers; display names are UI text.
4. Bitty and PTY details remain inside the terminal boundary.
5. `AgentSession` represents one AgentHub-managed runtime and identity.
6. `SessionManager` coordinates sessions but never manipulates the Textual DOM.
7. `AgentHubApp` owns mounting, visibility, focus, navigation, and application
   policy.
8. Hiding and unmounting are not interchangeable when a live terminal is
   involved.
9. Application keybindings do not belong in `AgentTerminal`.
10. Process-exit events are reported upward; the terminal does not decide
    application policy.
11. Working-directory support must use a real process-launch mechanism, not
    `cd ... && command` shell composition.
12. Runtime sessions and persistent records are separate concepts.
13. Keep current architectural domains in dedicated packages, but do not add
    empty placeholder packages, persistence, or `TerminalProfile` prematurely.
14. Preserve current one-session behavior while introducing the new boundaries.

## Quick Context for Future Conversations and Models

If only a compact summary is needed, use this:

```text
AgentHub is a Textual TUI that manages native coding-agent terminal sessions.
It embeds each agent through AgentTerminal → textual-tty → bittty/PTY; it does
not recreate agent UIs.

Harness        = immutable agent description and semantic terminal behavior
Terminal       = native-terminal adapter and Bitty boundary
Session        = AgentHub identity + cwd + harness + terminal runtime
SessionManager = session collection/lifecycle coordinator; no DOM or Bitty
App            = Textual DOM, visibility, focus, navigation, and policy

AgentSession conceptually owns its terminal runtime. AgentHubApp owns where and
how the terminal widget is mounted. Because textual-tty starts a process on
mount and stops it on unmount, session switching should hide/show mounted
terminals rather than unmounting them; the core process-survival behavior is
covered by an integration test.

Current state: the harness/terminal/session/manager boundaries are implemented
and tested while the UI still shows one fullscreen OpenCode session. Two hidden
or visible mounted terminal processes have been proven to survive switching and
shut down with their app. Next: add proper working-directory launching, finish
the remaining lifecycle validation, then add the sidebar and switching.
Persistence and native resume are deferred.
```
