"""Unit coverage for native clipboard handling in the session-name modal."""

import subprocess
from unittest.mock import patch

from agenthub.ui.modals.session_name import _read_system_clipboard, _system_clipboard_command


def test_wayland_clipboard_command_requests_text_content() -> None:
    """Wayland paste must not request an image clipboard's default MIME type."""

    with (
        patch.dict("os.environ", {"WAYLAND_DISPLAY": "wayland-1"}),
        patch("agenthub.ui.modals.session_name.shutil.which", return_value="/usr/bin/wl-paste"),
    ):
        assert _system_clipboard_command() == (
            "wl-paste",
            "--no-newline",
            "--type",
            "text",
        )


def test_system_clipboard_ignores_non_text_content() -> None:
    """Image clipboard bytes must not be decoded or inserted as a name."""

    png_bytes = b"\x89PNG\r\n\x1a\n"
    completed = subprocess.CompletedProcess(
        args=("wl-paste", "--no-newline", "--type", "text"),
        returncode=0,
        stdout=png_bytes,
        stderr=b"",
    )

    with (
        patch(
            "agenthub.ui.modals.session_name._system_clipboard_command",
            return_value=completed.args,
        ),
        patch("agenthub.ui.modals.session_name.subprocess.run", return_value=completed),
    ):
        assert _read_system_clipboard() == ""


def test_system_clipboard_decodes_utf8_text() -> None:
    """Valid UTF-8 clipboard bytes remain available to Ctrl+V."""

    completed = subprocess.CompletedProcess(
        args=("wl-paste", "--no-newline", "--type", "text"),
        returncode=0,
        stdout=b"AgentHub Refactor",
        stderr=b"",
    )

    with (
        patch(
            "agenthub.ui.modals.session_name._system_clipboard_command",
            return_value=completed.args,
        ),
        patch("agenthub.ui.modals.session_name.subprocess.run", return_value=completed),
    ):
        assert _read_system_clipboard() == "AgentHub Refactor"
