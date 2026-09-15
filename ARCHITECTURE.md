# AgentHub Architecture

This document is the architectural source of truth for AgentHub maintainers,
contributors, coding agents, and future design discussions. It separates
accepted boundaries from implementation hypotheses and deferred capabilities.

For installation and a concise product overview, see [README.md](README.md).

## Product Goal

AgentHub is a Textual-based terminal user interface for managing multiple
terminal-native coding-agent sessions from one application.

> Manage multiple native coding-agent terminal sessions from one TUI.

AgentHub does **not** reimplement a coding agent's interface. Supported coding
agents continue to render and handle input in their native terminal interfaces.
AgentHub embeds those interfaces through `textual-tty` and `bittty`, and adds
session management around them.

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
- owns terminal-first Locked/Unlocked keyboard policy and priority candidates
  for Ctrl+G, Ctrl+N, Ctrl+P, Ctrl+Q, and sidebar-group focus;
- gates hub navigation through `check_action()` while a terminal is active so
  rejected key events continue unchanged to `AgentTerminal`;
- coordinates a registry-driven harness picker, required session-name modal,
  and directory picker from Ctrl+N, creating no runtime until all three are
  confirmed;
- lazily creates one Fish session for each Ctrl+S, then 1…9 shell slot;
- maps terminal-exit events back to their owning sessions, removes exited
  runtimes, releases their shell slots, and shows Home after an active exit.

`SessionManager` currently:

- creates and retains sessions in creation order;
- makes a new session active;
- selects existing sessions by ID;
- removes exited sessions and clears selection when the active session is removed;
- constructs terminal runtimes without mounting them.

`AgentSession` currently connects an AgentHub ID and name with its intended
working directory, explicit agent-or-shell kind, hosted CLI definition, and
terminal runtime. The same model is used for coding-agent and Fish sessions.

`AgentHarness` is immutable semantic data containing a stable ID, display name,
tuple command, and an optional terminal-independent scrolling policy. It does
not create widgets or import Bitty.

`AgentTerminal` currently:

- subclasses `textual_tty.Terminal`;
- consumes an `AgentHarness`;
- launches the harness in its session working directory through a shell-free
  child helper that replaces itself with the harness process;
- converts semantic key modifiers into Bitty constants;
- converts mouse-wheel movement into agent-specific transcript navigation;
- retains bounded styled normal-screen scrollback for harnesses without their
  own transcript-scroll policy, including top-anchored partial scroll regions;
- maps PageUp/PageDown to retained primary-screen history;
- awaits Bitty reader-task and child-process cleanup during unmount;
- associates process-exit messages with the terminal that emitted them;
- delegates terminal emulation and process interaction to
  `textual-tty`/`bittty`.

Two coding-agent harnesses are registered:

| Registry key | Command    | Default | Scroll policy |
| ------------ | ---------- | ------- | ------------- |
| `opencode`   | `opencode` | yes     | semantic transcript shortcuts |
| `codex`      | `codex`    | no      | native terminal behavior |

Fish is a built-in shell definition used directly by the fixed shell slots. It
is intentionally not part of the coding-agent harness registry.

OpenCode's current transcript-scroll policy is:

```text
scroll down → Ctrl+Alt+E
scroll up   → Ctrl+Alt+Y
wheel step  → send the selected shortcut three times
```

Codex 0.154.0 was observed using the primary screen with mouse tracking disabled
for its normal interface inside AgentHub's terminal boundary. Its Ctrl+T
transcript pager uses the alternate screen and provides native arrow,
PageUp/PageDown, and Home/End navigation. Codex therefore has no semantic wheel
shortcut configured: AgentHub retains styled normal-screen history and delegates
alternate-screen behavior to `textual-tty`.

When the child application has enabled terminal mouse tracking, the child owns
the wheel and `AgentTerminal` delegates to `textual-tty`. Otherwise AgentHub
sends a harness's configured transcript-scroll shortcuts. Harnesses without a
custom policy, such as Fish, use bounded styled history on the normal screen and
textual-tty's behavior inside alternate-screen applications.

### Current repository structure

The authoritative source and test layout is documented in
[Repository Structure](#repository-structure) below.

The core ownership boundaries, Home-first shell, persistent sidebar and status
bar, and switching runtime are now implemented. Normal startup creates no
session. Ctrl+N collects a registered harness, user-provided session name, and
working directory before creating the selected agent runtime.

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
    scroll: ScrollKeys | None
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
semantic session kind
        +
working directory
        +
harness definition
        +
terminal runtime
```

The implemented model is:

```python
class SessionKind(StrEnum):
    AGENT = "agent"
    SHELL = "shell"


@dataclass
class AgentSession:
    id: str
    name: str
    kind: SessionKind
    cwd: Path
    harness: AgentHarness
    terminal: AgentTerminal
```

Conceptual example:

```text
id:       session-1
name:     Auth Refactor
kind:     agent
cwd:      ~/Projects/backend
harness:  OpenCode
terminal: mounted OpenCode terminal runtime
```

The session conceptually owns the terminal runtime, but `AgentHubApp` remains
responsible for mounting that widget and controlling its visibility in the
Textual DOM.

`SessionKind` describes semantic identity independently from keyboard shortcut
addressability. The Fish slot map answers which Ctrl+digit opens a session; it
does not decide whether a session is an agent or shell. Do not add
lifecycle-state enums, native harness session IDs, persistence records, or
separate runtime objects until stopped sessions are retained or another
implementation need requires them.

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
- creation, selection, and logical removal;
- lookup and enumeration;
- eventually stopping and restarting once those lifecycle operations
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
        kind: SessionKind,
        cwd: Path,
        harness: AgentHarness,
    ) -> AgentSession:
        ...

    def select(self, session_id: str) -> AgentSession:
        ...

    def remove(self, session_id: str) -> AgentSession:
        ...

    @property
    def sessions(self) -> tuple[AgentSession, ...]:
        ...

    @property
    def active_session(self) -> AgentSession | None:
        ...
```

Session IDs are generated internally, sessions are returned in creation order,
and new sessions become active. Removing an inactive session preserves the
selection; removing the active session clears selection so Home can become the
neutral view. Selecting or removing an unknown ID raises `KeyError`.

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
- keyboard-ownership policy and application keybindings;
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

Application shortcuts belong at this layer, but are enabled only when AgentHub
owns the keyboard:

```text
Ctrl+G toggles keyboard ownership
   │
   ├── Locked + active terminal → other hub actions fail check_action()
   │                              and their original keys reach the PTY
   │
   └── Unlocked → Ctrl+N opens the New Agent Session modal flow,
                  Ctrl+A/Ctrl+S focus a sidebar group, and a following plain
                  digit selects its numbered entry
```

Home is the intentional exception: with no active terminal, application
shortcuts work even while the authoritative mode remains Locked. Ctrl+A followed
by 1…9 selects a numbered agent; Ctrl+S followed by 1…9 opens or selects a Fish
slot. Ctrl+digit combinations remain unbound by AgentHub and reach the active
terminal.

This policy does not belong inside `AgentTerminal`; that boundary continues to
forward terminal input without knowing AgentHub navigation rules.

When Ctrl+G enters Locked mode with a live active terminal behind a modal, the
app dismisses that modal as cancellation before restoring terminal focus. This
includes any stage of the New Agent Session flow and ensures no partial
runtime is created. On Home, where there is no terminal to receive ownership,
the active modal remains open under the existing Home shortcut exception.

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

The implemented process-exit flow is:

```text
AgentTerminal emits ProcessExited
        │
        ▼
AgentHubApp resolves the affected AgentSession
        │
        ▼
SessionManager updates session/runtime coordination
        │
        ├── remove the exited session
        ├── release its Ctrl+S shell slot, if any
        ├── keep an active sibling visible when a hidden child exited
        └── show Home when the active child exited
```

The app resolves the Textual message sender to its owning session, coordinates
manager mutation with DOM removal, and keeps AgentHub running even when no
sessions remain. Home uses contextual guidance when other live sessions remain.
The terminal reports process exit but does not know about the manager, slot
mapping, selection, Home, or application quit policy.

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
directory both when constructed and immediately before mount. The New Agent
Session workflow uses a directory-only Textual `DirectoryTree` rooted at the
user's home directory to collect that launch path.

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
│                      │ Contextual session guidance        │
│                      │ Shortcut quick reference           │
├──────────────────────┴────────────────────────────────────┤
│ Sessions 0   Agents 0             ○ Unlocked  Ctrl+G Lock │
└───────────────────────────────────────────────────────────┘
```

The status bar keeps session and running-agent metrics on the left while the
keyboard-ownership state and Ctrl+G action remain grouped on the right.
The Home screen is a content view inside the application shell rather than a
separate Textual screen stack entry. This keeps shared navigation and status
chrome mounted while future content changes inside the `ContentSwitcher`.
Agent creation begins as a keyboard action and is configured through three small
modal screens:

```text
Ctrl+N
   │
   ▼
HarnessSelectionModal
   │ stable harness ID or cancellation
   ▼
AgentHubApp resolves registry
   │ selected harness
   ▼
SessionNameModal
   │ trimmed non-empty name or cancellation
   ▼
WorkingDirectoryModal
   │ confirmed normalized Path or cancellation
   ▼
AgentHubApp._create_agent_session(...)
   │
   ▼
_create_and_mount_session(...)
```

The harness picker derives its entries from the coding-agent registry, the name
modal displays the selected harness while collecting the AgentHub session name,
and the directory modal presents a folder-only tree. All three modals only
return user choices. `AgentHubApp` owns their sequencing, registry resolution,
and eventual runtime creation. Cancelling any stage creates nothing and leaves
the previous Home or live-session state usable.

The directory tree excludes dot-prefixed folders by default. Ctrl+H toggles
those folders and reloads the native tree while preserving expansion and cursor
state where the remaining paths permit it. Regular files remain excluded in
both modes. Right expands a folder on the first press and focuses its first
child on the second; Left collapses an expanded folder on the first press and
moves to its parent on the next.

Typing while the directory tree is focused applies a case-insensitive substring
filter to the immediate children of the current directory level. Ordinary spaces
are accepted after the query begins, and Backspace edits the query. The modal
displays both the query and its directory scope. The first alphabetically sorted
match receives the tree cursor automatically. When no matches remain, the scope
node is focused as a navigation fallback but cannot be confirmed until the query
changes or is cleared. The filter is local rather than a recursive filesystem
search. Entering a filtered directory with Right clears the previous query, so
subsequent typing filters the newly entered directory. Filtering also composes
with the current Ctrl+H hidden-directory state; hiding an active hidden scope
clears its filter and focuses the nearest ancestor that remains visible.

Textual 8.2.8 normally loads `DirectoryTree` entries through a threaded worker.
Under the project's Python 3.13 runtime, that worker prevents the event loop's
default executor from shutting down after the picker is used. `FolderTree`
therefore retains Textual's loading queue and filesystem error handling while
performing directory scans and entry checks in cooperative async handlers. This
version-sensitive adapter behavior is protected by integration tests.

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

The sidebar always renders `AGENTS` and `SHELLS` as equal-height sections, even
when either collection is empty. Both collections use `AgentSession`, one
`SessionManager`, and the same selected-session message.
The first nine agent rows use creation-order numbers selected through Ctrl+A,
then 1…9. Fish rows display their stable slot numbers and are opened or selected
through Ctrl+S, then 1…9. Agent sessions remain selectable directly from the
sidebar. The sidebar does not operate directly on `SessionManager` or terminal
internals. Ctrl+N uses the agent-only harness, name, and working-directory modal
flow; Fish creation continues to use the independent fixed-slot workflow.

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
│   ├── codex.py         # Codex definition
│   ├── fish.py          # Fish shell-slot definition
│   ├── model.py         # immutable semantic models
│   ├── opencode.py      # OpenCode definition
│   └── registry.py      # built-in harness lookup
├── sessions/
│   ├── __init__.py      # public session API
│   ├── model.py         # AgentSession runtime model
│   └── manager.py       # session coordination
├── terminal/
│   ├── __init__.py
│   ├── scrollback.py     # bounded styled history for plain shells
│   └── widget.py        # textual-tty/Bitty adapter
└── ui/
    ├── __init__.py
    ├── app.tcss         # persistent application-shell layout
    ├── bindings.py      # Textual bindings and shared shortcut metadata
    ├── theme.tcss       # shared component and Textual overlay styles
    ├── modals/
    │   ├── __init__.py
    │   ├── harness_selection.py   # registry-driven agent harness picker
    │   ├── harness_selection.tcss # compact picker presentation
    │   ├── session_name.py        # required AgentHub session name input
    │   ├── session_name.tcss      # compact name-prompt presentation
    │   ├── working_directory.py   # directory-only tree picker
    │   └── working_directory.tcss # directory-picker presentation
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
│   ├── test_session_name_modal.py
│   ├── test_terminal.py
│   └── test_working_directory_modal.py
└── integration/
    ├── test_app_lifecycle.py
    ├── test_command_palette.py
    ├── test_home_screen.py
    ├── test_keyboard_ownership.py
    ├── test_new_session_modals.py
    ├── test_session_creation_shortcuts.py
    ├── test_sidebar_groups.py
    ├── test_session_switching.py
    └── test_terminal_lifecycle.py
```

Packages are appropriate here because harnesses, sessions, and terminal hosting
are already distinct architectural concepts with multiple responsibilities or
expected implementations. Imports elsewhere should prefer the package public
APIs rather than reaching into `model.py`, `manager.py`, or individual harness
modules.

Do not create empty `widgets/`, `persistence/`, or `config/` packages yet. Add
those when the corresponding implementation begins.

The governing rule is:

> Establish packages for real architectural domains early, but do not create
> empty placeholder layers or speculative abstractions.

## Implementation Progress and Sequence

The architectural foundation is implemented:

1. `AgentHarness` is immutable semantic data with stable identity.
2. Bitty translation is isolated inside `AgentTerminal`.
3. AgentHub starts Unlocked; Ctrl+G toggles keyboard ownership, and hub actions
   fall through to the active terminal while locked.
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
   responsive Home landing state, clean zero-session sidebar, and real status bar
   establish the shared UI foundation.
9. Sidebar presentation accepts `AGENTS` and `SHELLS` collections backed by the
   same manager and selection flow.
10. Ctrl+N opens a registry-driven harness picker followed by a required
    session-name prompt and working-directory browser; confirming all three
    creates and focuses the selected agent. Ctrl+A or Ctrl+S followed by 1…9
    selects numbered agents or lazily creates and selects stable Fish slots.
11. Sessions carry explicit agent-or-shell identity, while the separate slot map
    only assigns shell keyboard shortcuts.
12. Exited runtimes are removed, active exits return to contextual Home, hidden
    exits do not interrupt the current terminal, and Fish slots become reusable.

The remaining sequence is:

1. Add explicit terminal lifecycle operations before user-initiated stop or
   restart of live sessions.
2. Add persistence and native session resumption only when the runtime model is
   stable.

## Validation Tasks

Validated with the installed dependency versions:

- Terminal A and Terminal B can remain mounted simultaneously.
- Hiding Terminal A does not unmount it or terminate its process.
- Focus can move from the hidden terminal to the visible terminal.
- Only the focused terminal receives keyboard input.
- Locked priority candidates rejected by `check_action()` reach the focused
  terminal's PTY unchanged, while Unlocked candidates execute hub actions.
- Ctrl+G changes the visible ownership state in both directions and never
  reaches the child terminal.
- Locking with an active terminal dismisses an open New Agent Session modal at
  any stage as cancellation and restores terminal focus; Home modals remain
  open.
- The directory picker displays folders while hiding ordinary files, toggles
  dot-prefixed folders with Ctrl+H, and shuts down its loading workers cleanly
  after confirmation or cancellation.
- Hidden terminals continue buffering output and retain their screen state.
- A terminal-exit event can be mapped to the exact owning session.
- Active exits return to Home, while hidden exits are removed without changing
  the current view or focus.
- Exited Fish slots are released and can create fresh shell runtimes.
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
- manager invariants, active-session selection, and logical removal;
- behavior when selecting or removing an unknown session;
- terminal semantic-key to Bitty translation;
- application creation with one managed session;
- launch-directory validation and shell-free command wrapping;
- concurrent child processes using distinct working directories;
- hidden mounted terminal survival;
- focus switching between mounted terminals;
- hidden output buffering and restored screen state;
- keyboard input isolation;
- Locked/Unlocked keyboard fall-through at the real PTY-write boundary;
- Home shortcut behavior without an active terminal;
- registry-derived harness selection and stable-ID modal results;
- required, trimmed user-provided session names and cancellation at all stages;
- directory-only browsing and normalized `Path` selection;
- deferred runtime creation until all three New Agent Session modals are confirmed;
- child-process cwd inheritance from the directory picker;
- stable Fish-slot navigation with persistent sidebar groups;
- process-exit routing to the owning session;
- active-exit navigation to Home and silent hidden-exit cleanup;
- shell-slot release and recreation after process exit;
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
kind
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
5. `AgentSession` represents one AgentHub-managed runtime with explicit semantic
   identity; keyboard slot assignment remains separate.
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
15. AgentHub starts Unlocked for immediate navigation; when explicitly Locked,
    only Ctrl+G may be intercepted and every other key belongs to the terminal.

## Quick Context for Future Conversations and Models

If only a compact summary is needed, use this:

```text
AgentHub is a Textual TUI that manages native coding-agent terminal sessions.
It embeds each agent through AgentTerminal → textual-tty → bittty/PTY; it does
not recreate agent UIs.

Harness        = immutable agent description and semantic terminal behavior
Terminal       = native-terminal adapter and Bitty boundary
Session        = AgentHub identity + kind + cwd + harness + terminal runtime
SessionManager = session collection/lifecycle coordinator; no DOM or Bitty
App            = Textual DOM, visibility, focus, navigation, and policy

AgentSession conceptually owns its terminal runtime. AgentHubApp owns where and
how the terminal widget is mounted. Because textual-tty starts a process on
mount and stops it on unmount, session switching should hide/show mounted
terminals rather than unmounting them; the core process-survival behavior is
covered by an integration test.

Current state: the harness/terminal/session/manager boundaries, Home-first
application shell, persistent sidebar and status bar, Locked/Unlocked keyboard
ownership, grouped sidebar presentation, registry-driven OpenCode and Codex
selection, required session naming, working-directory browsing, fixed Fish
slots, explicit session kinds, exited-runtime cleanup, and multi-session
switching runtime are implemented and tested. Normal startup and incomplete or
cancelled modal flows create no session or child process. Multiple terminals
have been proven to survive repeated switching, retain hidden output and screen
state, isolate input, run concurrently in distinct working directories, and
shut down with the app. Active exits return to Home, hidden exits are removed
without interrupting the current terminal, and Fish slots become reusable.
Locked hub shortcuts have been proven to fall through at the PTY-write
boundary. Next: add explicit terminal lifecycle operations before user-initiated
stop or restart of live sessions. Persistence and native resume are deferred.
```
