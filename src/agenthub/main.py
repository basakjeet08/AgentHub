"""Entry point: construct the app and run Textual's event loop."""

from agenthub.app import AgentHubApp


def main() -> None:
    """Launch AgentHub (installed as the `agenthub` shell command)."""

    AgentHubApp().run()
