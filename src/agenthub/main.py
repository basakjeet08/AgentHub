"""Entry point for the AgentHub TUI and provider hook helpers."""

import argparse
import sys
from collections.abc import Sequence

from agenthub.activity import run_codex_activity_hook


def _argument_parser() -> argparse.ArgumentParser:
    """Build the command parser without affecting the no-argument TUI path."""

    parser = argparse.ArgumentParser(prog="agenthub")
    commands = parser.add_subparsers(dest="command", required=True)
    activity_hook = commands.add_parser(
        "activity-hook",
        help="Run a provider activity hook helper.",
    )
    activity_hook.add_argument("provider", choices=("codex",))
    return parser


def main(argv: Sequence[str] | None = None) -> int | None:
    """Launch AgentHub or one of its non-interactive provider helpers."""

    arguments = list(sys.argv[1:] if argv is None else argv)
    if not arguments:
        from agenthub.app import AgentHubApp

        AgentHubApp().run()
        return None

    options = _argument_parser().parse_args(arguments)
    if options.command == "activity-hook" and options.provider == "codex":
        return run_codex_activity_hook()

    raise AssertionError("argparse accepted an unsupported AgentHub command")


if __name__ == "__main__":
    raise SystemExit(main())
