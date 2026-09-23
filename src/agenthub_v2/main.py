"""Entry point for the AgentHub TUI application."""

from agenthub_v2.session import SessionController


def main() -> int | None:
    """Main entry point for the application."""

    # Create the application controller used by the UI.
    session_controller = SessionController()
    session_controller.discover_sessions()
    for session in session_controller.get_all_sessions():
        session_item = session_controller.get_session(session.id)
        print(f"{session_item.provider_id} : {session_item.name}")

        resume_command = session_controller.resume_command(session_item.id)
        print(f"Command : {resume_command}")

    return None
