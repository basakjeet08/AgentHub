"""Entry point for the AgentHub TUI application."""

from .presentation import AgentHubApp


def main() -> None:
    """Main entry point for the application."""

    AgentHubApp().run()
