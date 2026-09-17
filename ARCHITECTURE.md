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
   ├── AgentHubStatusBar
   └── native-session adapters → unloaded AgentSession entries
```

No `AgentTerminal`, PTY, or coding-agent process is created just to display
Home. Provider-specific adapters discover native conversations in the
background and normalize them into unloaded `AgentSession` objects. Selecting
one follows `SessionManager → AgentSession → AgentTerminal → textual-tty →
bittty / PTY → coding agent`.

### Current responsibilities

`AgentHubApp`:

- owns one `SessionManager`;
- shows neutral Home content while provider discovery runs independently;
- discovers Codex, OpenCode, Devin, and Antigravity conversations without
  allowing one provider failure to prevent startup;
- resumes unloaded conversations by exact native ID and reuses an existing
  terminal when one is already running;
- owns the persistent sidebar, main content area, and status bar shell;
- mounts every terminal runtime known at composition time inside a
  `ContentSwitcher`;
- owns the session sidebar, active-terminal visibility, and focus;
- routes sidebar selection through an activation operation that either resumes
  an unloaded session or shows its existing runtime;
- owns terminal-first Locked/Unlocked keyboard policy and priority candidates
  for Ctrl+G, Ctrl+N, Ctrl+P, Ctrl+Q, and sidebar-group focus;
- gates hub navigation through `check_action()` while a terminal is active so
  rejected key events continue unchanged to `AgentTerminal`;
- coordinates a registry-driven harness picker and directory picker from
  Ctrl+N, creating no runtime until both are confirmed;
- opens an Alt+M picker for explicit reconciliation of a selected fresh runtime
  with an unloaded discovered conversation from the same harness and cwd;
- creates Fish shell sessions via Ctrl+Shift+S with an optional name;
- maps terminal-exit events back to their owning sessions, reconciles an exited
  native-backed Agent with only its provider, removes disposable unidentified
  agents and shells, and shows Home after an active exit;
- owns focus-scoped Ctrl+D navigation and confirmation while delegating native
  deletion to the selected session's provider adapter.

`SessionManager` currently:

- creates and retains sessions in creation order;
- makes a new session active;
- selects existing sessions by ID;
- merges a user-selected unloaded native row into an active unidentified Agent
  while preserving the running terminal and AgentHub row identity;
- removes disposable exited sessions and clears selection when appropriate;
- constructs terminal runtimes without mounting them.
- retains discovered logical sessions without terminal runtimes;
- deduplicates native conversations by harness ID and native session ID;
- attaches and detaches disposable terminal runtimes;
- coordinates native-deletion state and removes a logical row only after the
  provider operation succeeds and absence is verified.

`AgentSession` currently connects an ephemeral AgentHub ID and name with its
native session ID, optional working directory, explicit agent-or-shell kind,
hosted CLI definition, lifecycle state, and optional terminal runtime. The same
model is used for coding-agent and Fish sessions; Fish has no native ID and is
not discovered.

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
- ensures every rendered terminal segment has an explicit Rich style before
  Textual applies global line filters;
- awaits Bitty reader-task and child-process cleanup during unmount;
- associates process-exit messages with the terminal that emitted them;
- delegates terminal emulation and process interaction to
  `textual-tty`/`bittty`.

Four coding-agent harnesses are registered:

| Registry key  | Command    | Icon | Default | Scroll policy |
| ------------- | ---------- | ---- | ------- | ------------- |
| `antigravity` | `agy`      | `✨` | no      | native terminal behavior |
| `codex`       | `codex`    | `🌀` | no      | native terminal behavior |
| `devin`       | `devin`    | `🟩` | no      | native terminal behavior |
| `opencode`    | `opencode` | `💻` | yes     | semantic transcript shortcuts |

Fish is a built-in shell definition used for shell sessions. It
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

Antigravity CLI 1.2.2 and Devin CLI 3000.10.27 were exercised through the same
native terminal path. Both launch interactively with their bare commands, use
the selected child working directory, survive resize and session switching,
and clean up through the existing process-exit flow. Antigravity's retained
primary-screen output and alternate-screen views fit the existing native
history policy. Devin's native model overlay likewise requires no semantic
transcript shortcut. Both therefore use `scroll=None`; AgentHub adds no
provider-specific terminal branches.

When the child application has enabled terminal mouse tracking, the child owns
the wheel and `AgentTerminal` delegates to `textual-tty`. Otherwise AgentHub
sends a harness's configured transcript-scroll shortcuts. Harnesses without a
custom policy, such as Fish, use bounded styled history on the normal screen and
textual-tty's behavior inside alternate-screen applications.

`textual-tty` may pad live rows with unstyled Rich segments. Textual's global
monochrome filter requires concrete styles, so `AgentTerminal` normalizes those
segments at the rendering boundary. This is a generic terminal compatibility
rule rather than a harness identity check.

### Current repository structure

The authoritative source and test layout is documented in
[Repository Structure](#repository-structure) below.

The core ownership boundaries, Home-first shell, persistent sidebar and status
bar, native-session discovery and exact-ID resume, and switching runtime are
now implemented. Normal startup creates no terminal or child process. Ctrl+N
creates a fresh native CLI runtime with a temporary AgentHub label and no known
native session ID.

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
    icon: str = ""
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
    icon="💻",
)
```

Antigravity, Codex, and Devin use the same model with `scroll=None`; adding
each new harness required only its immutable definition, public export,
registry entry, and tests. Authentication, models, prompts, tools, permissions,
and provider behavior remain owned by each native CLI.

The stable `id` is used by code, configuration, CLI arguments, and eventual
persistence. `display_name` and `icon` are used by the UI (with `icon` displayed
alongside session names in the sidebar). A tuple keeps `command` actually
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

`AgentSession` represents one in-memory logical conversation and its optional
AgentHub-managed runtime.
It connects:

```text
AgentHub identity
        +
semantic session kind
        +
optional working directory
        +
harness definition
        +
native session identity
        +
optional terminal runtime
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
    cwd: Path | None
    harness: AgentHarness
    terminal: AgentTerminal | None
    native_session_id: str | None
    state: SessionState
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

The session conceptually owns an attached terminal runtime when loaded, but
`AgentHubApp` remains responsible for constructing and mounting that widget and
controlling its visibility in the Textual DOM. Discovered sessions begin with
`terminal=None` and `state=UNLOADED`.

`SessionKind` describes semantic identity independently from presentation.
It decides whether a session is an agent or shell. Native IDs and
lifecycle state are now required because logical sessions can exist without a
running terminal. Persistence records and a separate runtime object remain
unnecessary.

Conceptually:

```text
AgentSession = in-memory native conversation + optional runtime
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
                  Alt+M opens explicit native-session linking for an eligible
                  runtime, Ctrl+A/Ctrl+S focus a sidebar group, and a following
                  plain digit selects its numbered entry
```

Home is the intentional exception: with no active terminal, application
shortcuts work even while the authoritative mode remains Locked. In the sidebar,
Ctrl+A focuses agents where digits 1…9 move highlight and Enter activates; Ctrl+S
focuses shells for arrow-key navigation. Ctrl+Shift+S opens shell creation.
Ctrl+digit combinations remain unbound by AgentHub and reach the active terminal.

Ctrl+D is handled by AgentHub only when the AGENTS option list has actual focus,
and it targets that list's highlighted row. When a terminal has focus, the
priority binding is rejected so the original Ctrl+D reaches the PTY unchanged.
Shells do not participate in native deletion.

Permanent deletion follows this ownership sequence:

```text
highlighted native-backed Agent
        ↓ confirmation
SessionManager enters DELETING and detaches runtime
        ↓
AgentHubApp unmounts/stops the terminal
        ↓
NativeSessionAdapter.delete(exact native ID)
        ↓
same-provider discovery verifies absence
        ├── absent        → SessionManager removes logical row
        └── present/error → preserve native ID and return row to UNLOADED
```

Provider-specific commands and failures remain inside native-session adapters;
the app contains no harness-ID branches.

This policy does not belong inside `AgentTerminal`; that boundary continues to
forward terminal input without knowing AgentHub navigation rules.

When Ctrl+G enters Locked mode with a live active terminal behind a modal, the
app dismisses that modal as cancellation before restoring terminal focus. This
includes any stage of the New Agent Session flow and the native-session link
picker. New-session cancellation creates no partial runtime, and link
cancellation changes neither row. On Home, where there is no terminal to
receive ownership, the active modal remains open under the existing Home
shortcut exception.

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
        ├── native-backed Agent → detach terminal, mark unloaded, reconcile provider
        │                         ├── native ID remains → retain/update row
        │                         └── native ID absent  → remove stale row
        ├── unidentified Agent or Shell → remove the session
        ├── keep an active sibling visible when a hidden child exited
        └── show Home when the active child exited
```

The app resolves the Textual message sender to its owning session, coordinates
manager mutation with DOM removal, and keeps AgentHub running even when no
sessions remain. Home uses contextual guidance when other live sessions remain.
The terminal reports process exit but does not know about the manager,
selection, Home, or application quit policy.

Exit reconciliation uses the same manager reconciliation as startup and
Ctrl+Shift+R, but is scoped to the exiting session's harness. A provider failure
leaves the row unloaded. Fresh Agents without a native ID retain the disposable
exit path and do not trigger discovery.

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

## System Clipboard

`agenthub.clipboard` is the only module that talks to desktop clipboard
utilities. It resolves the first available backend (`wl-paste`, `xclip`,
`xsel`, `pbpaste`) and exposes an async `read_clipboard()` (and backwards-compatible
`read_clipboard_text()`) that never blocks the Textual event loop. It categorizes
clipboard content into four semantic kinds:

- `TEXT`: Decodable UTF-8 text payload ready for terminal paste.
- `EMPTY`: Clipboard is accessible but contains no data.
- `NON_TEXT`: Clipboard contains non-text or image data (e.g. `image/png`, binary bytes).
- `UNAVAILABLE`: No functional system clipboard backend is installed or reachable.

The desired dependency boundary is:

```text
OS clipboard
     ↓
agenthub.clipboard (inspect kind & content)
     ↓
AgentTerminal (focused Ctrl+V)
 ├── TEXT → textual-tty input_paste() → Bitty → PTY
 ├── EMPTY → no-op
 ├── NON_TEXT → forward_ctrl_v() → Bitty (KEY_MOD_CTRL) → PTY (harness handles image)
 └── UNAVAILABLE → fallback to AgentHub internal clipboard / warning
```

`AgentTerminal` owns Ctrl+V while focused: it inspects the system clipboard in a
worker. For textual content, it delivers the text through the terminal's native paste port, falling
back to AgentHub's internal clipboard when no desktop backend exists. For non-text or image
content, it forwards `Ctrl+V` through Bitty directly to the PTY so that native harnesses
(such as OpenCode or Codex) can detect the image and perform their own file attachment workflow.
Textual `Input` widgets keep their own Ctrl+V semantics. Ctrl+V and outer-terminal
`events.Paste` input converge on one serialized writer that preserves a single
bracketed-paste envelope while draining partial non-blocking PTY writes.

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
Harness registry entry
├── command
└── semantic terminal policy
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
│ Sessions 0   Running 0            ○ Unlocked  Ctrl+G Lock │
└───────────────────────────────────────────────────────────┘
```

The status bar keeps session and running-agent metrics on the left while the
keyboard-ownership state and Ctrl+G action remain grouped on the right.
The Home screen is a content view inside the application shell rather than a
separate Textual screen stack entry. This keeps shared navigation and status
chrome mounted while future content changes inside the `ContentSwitcher`.
Agent creation begins as a keyboard action and is configured through two small
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
WorkingDirectoryModal
   │ confirmed normalized Path or cancellation
   ▼
AgentHubApp._create_agent_session(...)
   │
   ▼
_create_and_mount_session(...)
```

The harness picker derives its entries from the coding-agent registry, and the
directory modal presents a folder-only tree. Both modals only return user
choices. `AgentHubApp` owns their sequencing, registry resolution, and eventual
runtime creation. Fresh Agents use the display-only label `New session` and do
not receive an AgentHub-authored native title. Cancelling either stage creates
nothing and leaves the previous Home or live-session state usable.

Fresh runtime reconciliation is deliberately explicit rather than heuristic:

```text
Select running fresh Agent (native_session_id=None)
   │
   ▼ Alt+M
NativeSessionLinkModal
   │ same-harness, same-cwd, unloaded, unique-ID native rows only
   ▼ user selects one row
SessionManager.link_native_session(...)
   │
   ├── preserve pending AgentHub ID and terminal/process
   ├── adopt provider native ID and title
   └── remove the selected unloaded duplicate row
```

The picker shows only provider-owned titles. Native IDs remain internal, and
conversations from other working directories are excluded. Both rows are
revalidated on confirmation. If either changed, linking fails without a partial
merge. Later discovery matches the linked row by exact native identity, updates
provider metadata in place, and cannot recreate the duplicate.

The target of Alt+M follows keyboard context rather than terminal visibility:

```text
AGENTS list focused → highlighted Agent row
SHELLS list focused → reject linking
otherwise           → active Agent session
```

Sidebar cursor identity and active-session identity are independent. Linking a
highlighted hidden Agent preserves the currently active session and visible
terminal; it also preserves the linked row's cursor through sidebar
recomposition. Enter remains the operation that activates a highlighted row.

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

The sidebar always renders `AGENTS` and `SHELLS`, even when either collection is
empty, and allocates them 70% and 30% of the available section space
respectively. Both collections use `AgentSession`, one `SessionManager`, and the
Agent rows can be highlighted with Ctrl+A, then 1…9, and activated with Enter.
Shell rows are navigated with Ctrl+S and arrow keys, and activated with Enter.
Agent sessions remain selectable directly from the
sidebar. The sidebar does not operate directly on `SessionManager` or terminal
internals. Ctrl+N uses the agent-only harness and working-directory modal flow;
Ctrl+Shift+S opens the lightweight shell naming workflow.

## Repository Structure

The implemented architectural domains use dedicated packages so their public
boundaries remain stable as more harnesses and session behavior are added:

```text
src/agenthub/
├── __init__.py
├── _terminal_launcher.py # child-side cwd setup and exec
├── main.py              # entry point
├── app.py               # Textual application and DOM ownership
├── clipboard.py         # system-clipboard backend resolution and reads
├── harnesses/
│   ├── __init__.py      # public harness API
│   ├── antigravity.py   # Antigravity definition
│   ├── codex.py         # Codex definition
│   ├── devin.py         # Devin definition
│   ├── fish.py          # Fish shell definition
│   ├── model.py         # immutable semantic models
│   ├── opencode.py      # OpenCode definition
│   └── registry.py      # built-in harness lookup
├── native_sessions/
│   ├── __init__.py      # public native-session API
│   ├── _normalize.py     # shared provider-record validation
│   ├── _sqlite.py        # read-only provider database access
│   ├── adapter.py       # provider adapter protocol and failures
│   ├── model.py         # normalized discovery and launch models
│   ├── registry.py      # built-in adapter lookup
│   ├── antigravity.py   # Antigravity discovery/resume adapter
│   ├── codex.py         # Codex discovery/resume adapter
│   ├── devin.py         # Devin discovery/resume adapter
│   └── opencode.py      # OpenCode discovery/resume adapter
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
    │   ├── native_session_link.py # explicit native-session reconciliation
    │   ├── native_session_link.tcss # native-link picker presentation
    │   ├── session_name.py        # optional Fish shell session name input
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
│   ├── test_clipboard.py
│   ├── test_harnesses.py
│   ├── test_main.py
│   ├── test_native_session_adapters.py
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
    ├── test_native_session_discovery.py
    ├── test_session_creation_shortcuts.py
    ├── test_sidebar_groups.py
    ├── test_session_switching.py
    ├── test_terminal_lifecycle.py
    └── test_terminal_paste.py
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
4. `AgentSession` and `SessionManager` represent logical sessions and coordinate
   their optional runtimes.
5. The app starts on Home without constructing a terminal or child process,
   while native-session discovery populates unloaded logical sessions.
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
10. Ctrl+N opens a registry-driven harness picker followed by a
    working-directory browser; confirming both creates and focuses a fresh
    `New session` agent. Ctrl+A moves cursor highlight across numbered agents
    (Enter activates), and Ctrl+Shift+S creates named shells.
11. Sessions carry explicit agent-or-shell identity.
12. Native-backed Agents are unloaded and reconciled with only their provider
    after exit; unidentified Agents and shells are removed. Active exits return
    to contextual Home, and hidden exits do not interrupt the current terminal.
13. Antigravity and Devin are registry-driven harnesses using the same
    working-directory, session, terminal, switching, and cleanup paths as the
    existing coding agents.
14. Provider-specific adapters discover Codex, OpenCode, Devin, and Antigravity
    conversations, normalize them into unloaded sessions, and construct
    exact-ID resume launches on selection.
15. Alt+M explicitly links a selected fresh runtime to an eligible unloaded
    native row from the same harness and cwd without restarting its terminal.
16. Ctrl+D on the focused AGENTS list confirms provider-native deletion of the
    highlighted row, stops an attached runtime first, verifies provider absence,
    and preserves the logical row and native ID on failure.

The remaining sequence is:

1. Create and title native conversations through the provider adapters if a
   reliable provider-native mechanism becomes available.
2. Add a supported non-interactive Antigravity deletion entry point when its
   provider exposes one; other adapters use their native deletion commands.

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
- Exited shell sessions are removed cleanly from the manager and sidebar.
- Two concurrent children inherit distinct session working directories while
  AgentHub's own working directory remains unchanged.
- OpenCode, Codex, Antigravity, and Devin-shaped sessions coexist, preserve
  independent working directories, and remain alive across repeated switching.
- The real `agy` and `devin` CLIs launch in a selected repository, survive
  switching and resize, render their native interfaces, and exit through normal
  session cleanup without leaving ghost sidebar or manager state.
- Live terminal rows remain renderable when Textual's monochrome filter is
  active, including rows padded by `textual-tty` without an explicit style.
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
- provider-native discovery normalization and exact-ID resume launch specs;
- unloaded sidebar sessions, lazy terminal creation, and running-runtime reuse;
- independent provider-discovery failure containment;
- exact four-agent registry membership and alphabetically sorted picker output;
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
- complete Antigravity- and Devin-shaped generic modal/session creation flows;
- temporary `New session` labels and cancellation at both Agent creation stages;
- explicit same-harness, same-cwd native-session linking using provider titles;
- preservation of the fresh runtime's terminal object and process across a
  link, plus exact-ID de-duplication on later discovery;
- independent sidebar cursor and active-session identities, including linking
  a highlighted hidden Agent without switching the visible terminal;
- directory-only browsing and normalized `Path` selection;
- deferred runtime creation until both New Agent Session modals are confirmed;
- child-process cwd inheritance from the directory picker;
- shell navigation with persistent sidebar groups;
- process-exit routing to the owning session;
- active-exit navigation to Home, silent hidden-exit cleanup, and unloaded
  retention for native-backed Agents;
- shell session cleanup after process exit;
- missing-binary cleanup without a ghost session, sidebar row, or active-session
  reference;
- simultaneous four-harness switching without process restart or cwd leakage;
- terminal-row style normalization for compatibility with Textual line filters;
- warning-free reader-task and child-process cleanup during application
  shutdown.

Future tests should cover the installed `agenthub` command.

Automated tests that launch processes use a harmless controllable test command
or fake harness and do not require real provider authentication. Real CLI
acceptance remains an explicit local/manual check.

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

## Native Harness Resume

A human-readable AgentHub session name is not sufficient to resume a native
coding-agent conversation. Implemented resume support uses:

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

Provider-specific native-session adapters discover this metadata from each
harness and produce exact-ID launch specifications. The immutable
`AgentHarness` remains terminal presentation and default-command configuration;
it does not absorb provider storage or conversation lifecycle behavior.

Discovery is a synchronous adapter operation because providers use blocking
filesystem and SQLite APIs. `AgentHubApp` submits those operations to a small,
bounded executor owned only by startup discovery, then cooperatively polls the
result futures from its async worker. Session normalization and all Textual DOM
updates remain on the application event loop. This avoids both UI stalls and
the Python 3.13 default-executor shutdown behavior described above. Provider
timeouts stop AgentHub from waiting; they cannot forcibly terminate a Python
thread, so the read-only SQLite helpers retain short database timeouts and the
executor cancels work that has not started.

Provider state locations follow their native Linux configuration. Codex checks
`CODEX_SQLITE_HOME`, then `CODEX_HOME`, before `~/.codex`. Devin checks
`$XDG_DATA_HOME/devin/cli/sessions.db` before the conventional
`~/.local/share/devin/cli/sessions.db`, retaining the latter as a compatibility
fallback. Explicit adapter paths used by tests and embedding callers always
take precedence.

Ctrl+Shift+R schedules the same provider discovery pipeline after startup. A
successful provider result updates known native metadata, adds newly discovered
conversations, and removes unloaded entries that the provider no longer
reports. Sessions with attached runtimes are retained so re-sync never
interrupts a running terminal. Because a fresh Ctrl+N runtime has no native ID,
discovery does not guess its identity from title, cwd, timestamps, or ordering.
The native conversation is therefore added as a separate unloaded row when no
exact-ID match exists. Repeated discovery deduplicates that native-backed row by
`(harness_id, native_session_id)`. Failed providers retain their existing
entries. The user can then select the unidentified running row and press Alt+M.
Only unloaded native-backed rows from the same harness and cwd are offered;
provider ID and title are transferred to the existing running row, the selected
duplicate is removed, and the mounted terminal is preserved. This user choice
is the reconciliation evidence—AgentHub still never guesses from mutable
metadata. If the Agents list is focused, its highlighted row is the pending
runtime; otherwise the active Agent is used. Shell-list focus blocks the action.

## Architectural Rules

Future work should preserve these rules:

1. AgentHub manages native agent UIs; it does not reimplement them.
2. `AgentHarness` is immutable semantic configuration, not a widget factory.
3. Harness IDs are stable machine identifiers; display names are UI text.
4. Bitty and PTY details remain inside the terminal boundary.
5. `AgentSession` represents one in-memory logical conversation with an optional
   runtime.
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
Session        = native identity + kind + cwd + harness + optional runtime
SessionManager = session collection/lifecycle coordinator; no DOM or Bitty
App            = Textual DOM, visibility, focus, navigation, and policy

AgentSession conceptually owns its terminal runtime. AgentHubApp owns where and
how the terminal widget is mounted. Because textual-tty starts a process on
mount and stops it on unmount, session switching should hide/show mounted
terminals rather than unmounting them; the core process-survival behavior is
covered by an integration test.

Current state: native-session adapters discover Codex, OpenCode, Devin, and
Antigravity conversations at startup. They appear unloaded, resume by exact
native ID when selected, and reuse an already-running terminal. The
harness/terminal/session/manager boundaries, Home-first
application shell, persistent sidebar and status bar, Locked/Unlocked keyboard
ownership, grouped sidebar presentation, registry-driven Antigravity, Codex,
Devin, and OpenCode selection, required session naming, working-directory
browsing, shell creation and navigation, explicit session kinds, exited-runtime cleanup, and multi-session
switching runtime are implemented and tested. Normal startup and incomplete or
cancelled modal flows create no session or child process. Multiple terminals
have been proven to survive repeated switching, retain hidden output and screen
state, isolate input, run concurrently in distinct working directories, and
shut down with the app. Native-backed exits reconcile only their provider;
active exits return to Home, and hidden exits do not interrupt the current
terminal. Ctrl+D deletes only the highlighted native-backed Agent while the
AGENTS list is focused, and terminal-focused Ctrl+D still reaches the PTY.
Locked hub shortcuts have been proven to fall through at the PTY-write
boundary. Next: create native conversations through the adapters and add a
supported non-interactive Antigravity deletion entry point. AgentHub persistence
remains deferred.
```
