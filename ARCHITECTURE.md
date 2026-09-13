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

Normal startup now follows this path:

```text
main.py
   │
   ▼
AgentHubApp
   │
   ├── SessionSidebar
   ├── HomeScreen
   └── AgentHubStatusBar
```

No `AgentSession`, `AgentTerminal`, PTY, or coding-agent process is created just
to display Home. When sessions are explicitly present, the established runtime
path remains `SessionManager → AgentSession → AgentTerminal → textual-tty →
bittty / PTY → coding agent`.

### Current responsibilities

`AgentHubApp`:

- owns one `SessionManager`;
- starts with that manager empty and shows the neutral Home content;
- owns the persistent sidebar, main content area, and status bar shell;
- mounts every session known at composition time inside a `ContentSwitcher`;
- owns the session sidebar, active-terminal visibility, and focus;
- routes sidebar selection through one `show_session()` operation;
- owns a priority Ctrl+Q application binding;
- owns priority Ctrl+N and focus-navigation bindings, whose session-creation
  action is deliberately a stub until the New Session phase;
- maps terminal-exit events back to their owning sessions and exits when the
  only session's child process exits.

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
- launches the harness in its session working directory through a shell-free
  child helper that replaces itself with the harness process;
- converts semantic key modifiers into Bitty constants;
- converts mouse-wheel movement into agent-specific transcript navigation;
- awaits Bitty reader-task and child-process cleanup during unmount;
- associates process-exit messages with the terminal that emitted them;
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

The authoritative source and test layout is documented in
[Repository Structure](#repository-structure) below.

The core ownership boundaries, Home-first shell, persistent sidebar and status
bar, and switching runtime are now implemented. Normal startup creates no
session. The visible New Session controls are not wired to session creation yet.

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

Conceptual example:

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
- displaying Home when no session is active;
- maintaining real application-level status counts;
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

Automated integration tests now confirm with the installed Textual and
`textual-tty` versions that hiding a mounted terminal leaves its process alive,
hidden output continues to update retained screen state, input reaches only the
focused terminal, repeated switching restores the terminal view, and
application shutdown stops all mounted terminal processes.

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

The implemented launch behavior is:

```python
AgentTerminal(
    harness=OPENCODE,
    working_directory=Path("~/Projects/foo").expanduser(),
)
```

The installed `textual-tty.Terminal` constructor accepts a command but not a
working directory. `AgentTerminal` therefore launches a small packaged Python
helper inside the child PTY. The helper changes only its own working directory
and calls `os.execvp()` to replace itself with the harness command. There is no
long-lived wrapper process, shell composition, or process-wide directory change
inside AgentHub.

The terminal validates that the normalized launch path exists and is a
directory both when constructed and immediately before mount. A user-facing
directory picker remains part of the New Session workflow.

`textual_tty.Terminal.cwd` already stores a child-reported OSC 7 path. AgentHub
therefore uses the distinct `working_directory` attribute for launch
configuration rather than changing the meaning of that inherited attribute.

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

## UI Relationship

Normal empty startup uses a persistent application shell:

```text
┌──────────────────────┬────────────────────────────────────┐
│ AgentHub sidebar     │ HomeScreen                         │
│                      │                                    │
│ + New Session        │ Empty-state guidance               │
│                      │ Shortcut quick reference           │
├──────────────────────┴────────────────────────────────────┤
│ Ready                       Sessions 0           Agents 0 │
└───────────────────────────────────────────────────────────┘
```

The Home screen is a content view inside the application shell rather than a
separate Textual screen stack entry. This keeps shared navigation and status
chrome mounted while future content changes inside the `ContentSwitcher`. The
New Session control lives in the persistent sidebar rather than being duplicated
inside Home.

The implemented sidebar-to-terminal relationship is conceptually:

```text
┌──────────────────────┬────────────────────────────────────┐
│ Sessions             │                                    │
│                      │                                    │
│ > Auth Refactor      │       Active AgentTerminal         │
│   API Cleanup        │                                    │
│   Payment Bug        │                                    │
│                      │                                    │
└──────────────────────┴────────────────────────────────────┘
```

The sidebar presents a New Session entry point and, only when sessions exist,
lists `AgentSession` objects and emits selected session IDs. It does not operate
directly on `SessionManager` or terminal internals. The sidebar New Session
control currently emits intent to an application-owned stub; the modal and
creation workflow remain future work.

## Repository Structure

The implemented architectural domains use dedicated packages so their public
boundaries remain stable as more harnesses and session behavior are added:

```text
src/agenthub/
├── __init__.py
├── _terminal_launcher.py # child-side cwd setup and exec
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
├── terminal/
│   ├── __init__.py
│   └── widget.py        # textual-tty/Bitty adapter
└── ui/
    ├── __init__.py
    ├── app.tcss         # persistent application-shell layout
    ├── bindings.py      # Textual bindings and shared shortcut metadata
    ├── theme.tcss       # shared component and Textual overlay styles
    ├── screens/
    │   ├── __init__.py
    │   ├── home.py      # neutral empty-state presentation and intent
    │   └── home.tcss    # responsive Home presentation
    └── panels/
        ├── __init__.py
        ├── sidebar.py   # session navigation panel
        ├── sidebar.tcss # sidebar presentation styles
        ├── status_bar.py   # real application state and counts
        └── status_bar.tcss # persistent status presentation

tests/
├── conftest.py          # shared harmless process fixture
├── unit/
│   ├── test_app.py
│   ├── test_harnesses.py
│   ├── test_main.py
│   ├── test_session_manager.py
│   └── test_terminal.py
└── integration/
    ├── test_app_lifecycle.py
    ├── test_command_palette.py
    ├── test_home_screen.py
    ├── test_session_switching.py
    └── test_terminal_lifecycle.py
```

Packages are appropriate here because harnesses, sessions, and terminal hosting
are already distinct architectural concepts with multiple responsibilities or
expected implementations. Imports elsewhere should prefer the package public
APIs rather than reaching into `model.py`, `manager.py`, or individual harness
modules.

Do not create empty `widgets/`, `modals/`, `screens/`, `persistence/`, or
`config/` packages yet. Add those when the corresponding implementation begins.

The governing rule is:

> Establish packages for real architectural domains early, but do not create
> empty placeholder layers or speculative abstractions.

## Implementation Progress and Sequence

The architectural foundation is implemented:

1. `AgentHarness` is immutable semantic data with stable identity.
2. Bitty translation is isolated inside `AgentTerminal`.
3. Ctrl+Q is an application-owned priority binding.
4. `AgentSession` and `SessionManager` represent and coordinate runtimes.
5. The app starts empty on Home without constructing a terminal or child
   process, while retaining support for sessions created before mount.
6. A minimal sidebar routes selection through one app-owned switching
   operation.
7. Integration tests prove that two manager-owned terminals remain mounted and
   running, hidden output and screen state survive switching, input is isolated
   to the active terminal, exit events map to the correct session, and app
   shutdown terminates both processes.
8. A persistent application shell, Textual's built-in Tokyo Night theme,
   responsive Home empty state, clean zero-session sidebar, and real status bar
   establish the shared UI foundation.

The remaining sequence is:

1. Add the user-facing New Session workflow behind the existing intent points
   so users can choose a harness and working directory.
2. Add explicit terminal lifecycle operations before session stop, restart, or
   removal.
3. Add persistence and native session resumption only when the runtime model is
   stable.

## Validation Tasks

Validated with the installed dependency versions:

- Terminal A and Terminal B can remain mounted simultaneously.
- Hiding Terminal A does not unmount it or terminate its process.
- Focus can move from the hidden terminal to the visible terminal.
- Only the focused terminal receives keyboard input.
- Hidden terminals continue buffering output and retain their screen state.
- A terminal-exit event can be mapped to the exact owning session.
- Two concurrent children inherit distinct session working directories while
  AgentHub's own working directory remains unchanged.
- App shutdown terminates all owned child processes reliably.

These experiments may influence implementation details, but they do not by
themselves invalidate the ownership model.

## Testing Direction

Tests are grouped by execution boundary:

- `tests/unit/` covers models, coordination, configuration, and adapter logic
  without running a live Textual application or child process.
- `tests/integration/` exercises mounted Textual widgets and their child-process
  lifecycle.
- `tests/conftest.py` provides the shared harmless process harness used by both
  tiers.

The tiers can be run independently with `python -m pytest tests/unit` and
`python -m pytest tests/integration`.

The architectural foundation now has automated coverage for:

- immutable harness configuration and stable registry identity;
- manager invariants and active-session selection;
- behavior when selecting an unknown session;
- terminal semantic-key to Bitty translation;
- application creation with one managed session;
- launch-directory validation and shell-free command wrapping;
- concurrent child processes using distinct working directories;
- hidden mounted terminal survival;
- focus switching between mounted terminals;
- hidden output buffering and restored screen state;
- keyboard input isolation;
- process-exit routing to the owning session;
- warning-free reader-task and child-process cleanup during application
  shutdown.

Future tests should cover the installed `agenthub` command.

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
14. Normal startup must show AgentHub itself without requiring a harness or
    child process to launch.

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

Current state: the harness/terminal/session/manager boundaries, Home-first
application shell, persistent sidebar and status bar, and multi-session
switching runtime are implemented and tested. Normal startup creates no session
or child process. Multiple explicitly created terminals have been proven to
survive repeated switching, retain hidden output and screen state, isolate
input, route exit events to their owning sessions, run concurrently in distinct
working directories, and shut down with the app. Next: wire the existing New
Session intent points to the incremental creation workflow. Persistence and
native resume are deferred.
```
