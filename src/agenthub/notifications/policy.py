"""Policy for turning Agent activity transitions into notifications."""

from agenthub.activity import AgentActivity

from .model import DesktopNotification


def notification_for_activity_transition(
    previous: AgentActivity,
    current: AgentActivity,
    *,
    harness_name: str,
    session_title: str,
    is_loaded_agent: bool,
) -> DesktopNotification | None:
    """Return a notification only for a loaded Agent's new attention state."""

    if previous is current or not is_loaded_agent:
        return None

    if current is AgentActivity.NEEDS_INPUT:
        title = f"{harness_name} needs input"
    elif current is AgentActivity.DONE:
        title = f"{harness_name} finished"
    else:
        return None

    return DesktopNotification(title=title, message=session_title)
