"""Entry point for the AgentHub TUI and provider hook helpers."""

import argparse
import sys
from collections.abc import Sequence

from agenthub.providers import ACTIVITY_ADAPTERS


def _argument_parser() -> argparse.ArgumentParser:
    """Build the command parser without affecting the no-argument TUI path."""

    parser = argparse.ArgumentParser(prog="agenthub")
    commands = parser.add_subparsers(dest="command", required=True)
    activity_hook = commands.add_parser(
        "activity-hook",
        help="Run a provider activity hook helper.",
    )
    activity_hook.add_argument("provider", choices=tuple(ACTIVITY_ADAPTERS))
    activity_hook.add_argument("event", nargs="?")
    return parser


def main(argv: Sequence[str] | None = None) -> int | None:
    """Launch AgentHub or one of its non-interactive provider helpers."""

    arguments = list(sys.argv[1:] if argv is None else argv)
    if not arguments:
        from agenthub.app import AgentHubApp

        AgentHubApp().run()
        return None

    parser = _argument_parser()
    options = parser.parse_args(arguments)
    if options.command == "activity-hook":
        try:
            return ACTIVITY_ADAPTERS[options.provider].run_hook(options.event)
        except (TypeError, ValueError) as error:
            parser.error(str(error))

    raise AssertionError("argparse accepted an unsupported AgentHub command")


if __name__ == "__main__":
    raise SystemExit(main())
