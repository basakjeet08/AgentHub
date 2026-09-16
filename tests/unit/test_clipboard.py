"""Unit coverage for the system-clipboard backend boundary."""

import asyncio
from unittest.mock import AsyncMock, Mock, patch

import pytest

from agenthub import clipboard


def test_wayland_prefers_wl_paste_text() -> None:
    """Wayland paste must not request an image clipboard's default MIME type."""

    with (
        patch.dict("os.environ", {"WAYLAND_DISPLAY": "wayland-1", "DISPLAY": ""}),
        patch("agenthub.clipboard.shutil.which", return_value="/usr/bin/wl-paste"),
    ):
        assert clipboard.resolve_clipboard_command() == (
            "wl-paste",
            "--no-newline",
        )


def test_wayland_resolves_wl_paste_list_types() -> None:
    with (
        patch.dict("os.environ", {"WAYLAND_DISPLAY": "wayland-1", "DISPLAY": ""}),
        patch("agenthub.clipboard.shutil.which", return_value="/usr/bin/wl-paste"),
    ):
        assert clipboard.resolve_clipboard_targets_command() == (
            "wl-paste",
            "--list-types",
        )


def test_wayland_without_wl_paste_falls_back_to_xclip() -> None:
    with (
        patch.dict("os.environ", {"WAYLAND_DISPLAY": "wayland-1", "DISPLAY": ":0"}),
        patch(
            "agenthub.clipboard.shutil.which",
            side_effect=lambda name: "/usr/bin/xclip" if name == "xclip" else None,
        ),
    ):
        assert clipboard.resolve_clipboard_command() == (
            "xclip",
            "-selection",
            "clipboard",
            "-o",
        )


def test_x11_resolves_xclip_targets() -> None:
    with (
        patch.dict("os.environ", {"WAYLAND_DISPLAY": "", "DISPLAY": ":0"}),
        patch(
            "agenthub.clipboard.shutil.which",
            side_effect=lambda name: "/usr/bin/xclip" if name == "xclip" else None,
        ),
    ):
        assert clipboard.resolve_clipboard_targets_command() == (
            "xclip",
            "-selection",
            "clipboard",
            "-t",
            "TARGETS",
            "-o",
        )


def test_x11_without_xclip_falls_back_to_xsel() -> None:
    with (
        patch.dict("os.environ", {"WAYLAND_DISPLAY": "", "DISPLAY": ":0"}),
        patch(
            "agenthub.clipboard.shutil.which",
            side_effect=lambda name: "/usr/bin/xsel" if name == "xsel" else None,
        ),
    ):
        assert clipboard.resolve_clipboard_command() == (
            "xsel",
            "--clipboard",
            "--output",
        )


def test_macos_uses_pbpaste() -> None:
    with (
        patch.dict("os.environ", {"WAYLAND_DISPLAY": "", "DISPLAY": ""}),
        patch("agenthub.clipboard.sys.platform", "darwin"),
        patch(
            "agenthub.clipboard.shutil.which",
            side_effect=lambda name: "/usr/bin/pbpaste" if name == "pbpaste" else None,
        ),
    ):
        assert clipboard.resolve_clipboard_command() == ("pbpaste",)


def test_no_backend_available_resolves_to_none() -> None:
    with (
        patch.dict("os.environ", {"WAYLAND_DISPLAY": "", "DISPLAY": ""}),
        patch("agenthub.clipboard.sys.platform", "linux"),
        patch("agenthub.clipboard.shutil.which", return_value=None),
    ):
        assert clipboard.resolve_clipboard_command() is None
        assert clipboard.resolve_clipboard_targets_command() is None


def _fake_process(stdout: bytes = b"", stderr: bytes = b"", returncode: int = 0) -> Mock:
    process = Mock()
    process.communicate = AsyncMock(return_value=(stdout, stderr))
    process.returncode = returncode
    process.kill = Mock()
    process.wait = AsyncMock(return_value=returncode)
    return process


async def test_read_without_a_backend_returns_none() -> None:
    with patch("agenthub.clipboard.resolve_clipboard_command", return_value=None):
        assert await clipboard.read_clipboard_text() is None


async def test_read_clipboard_without_backend_returns_unavailable() -> None:
    with patch("agenthub.clipboard.resolve_clipboard_command", return_value=None):
        content = await clipboard.read_clipboard()
        assert content.kind == clipboard.ClipboardKind.UNAVAILABLE
        assert content.text is None


async def test_read_spawns_the_resolved_command_and_decodes_utf8() -> None:
    expected_text = "first line\ncafé 🐟\tCJK: 你好\n"
    targets_process = _fake_process(b"text/plain\nUTF8_STRING\n")
    read_process = _fake_process(expected_text.encode("utf-8"))

    with (
        patch(
            "agenthub.clipboard.resolve_clipboard_command",
            return_value=("wl-paste", "--no-newline"),
        ),
        patch(
            "agenthub.clipboard.asyncio.create_subprocess_exec",
            AsyncMock(side_effect=[targets_process, read_process]),
        ) as spawn,
    ):
        text = await clipboard.read_clipboard_text()

    assert text == expected_text
    assert spawn.await_count == 2


async def test_read_without_targets_backend_decodes_utf8() -> None:
    expected_text = "first line\ncafé 🐟\tCJK: 你好\n"
    read_process = _fake_process(expected_text.encode("utf-8"))

    with (
        patch(
            "agenthub.clipboard.resolve_clipboard_command",
            return_value=("xsel", "--clipboard", "--output"),
        ),
        patch(
            "agenthub.clipboard.asyncio.create_subprocess_exec",
            AsyncMock(return_value=read_process),
        ) as spawn,
    ):
        text = await clipboard.read_clipboard_text()

    assert text == expected_text
    spawn.assert_awaited_once_with(
        "xsel",
        "--clipboard",
        "--output",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )


async def test_read_clipboard_detects_wayland_image_types() -> None:
    process = _fake_process(stdout=b"image/png\n")

    with (
        patch(
            "agenthub.clipboard.resolve_clipboard_command",
            return_value=("wl-paste", "--no-newline"),
        ),
        patch(
            "agenthub.clipboard.asyncio.create_subprocess_exec",
            AsyncMock(return_value=process),
        ),
    ):
        content = await clipboard.read_clipboard()
        assert content.kind == clipboard.ClipboardKind.NON_TEXT
        assert content.text is None
        assert await clipboard.read_clipboard_text() is None


async def test_read_clipboard_wayland_empty_nothing_copied() -> None:
    process = _fake_process(stderr=b"Nothing is copied\n", returncode=1)

    with (
        patch(
            "agenthub.clipboard.resolve_clipboard_command",
            return_value=("wl-paste", "--no-newline"),
        ),
        patch(
            "agenthub.clipboard.asyncio.create_subprocess_exec",
            AsyncMock(return_value=process),
        ),
    ):
        content = await clipboard.read_clipboard()
        assert content.kind == clipboard.ClipboardKind.EMPTY
        assert content.text is None
        assert await clipboard.read_clipboard_text() == ""


async def test_read_clipboard_xclip_image_targets() -> None:
    process = _fake_process(stdout=b"TARGETS\nimage/png\n")

    with (
        patch(
            "agenthub.clipboard.resolve_clipboard_command",
            return_value=("xclip", "-selection", "clipboard", "-o"),
        ),
        patch(
            "agenthub.clipboard.asyncio.create_subprocess_exec",
            AsyncMock(return_value=process),
        ),
    ):
        content = await clipboard.read_clipboard()
        assert content.kind == clipboard.ClipboardKind.NON_TEXT


async def test_read_returns_empty_string_for_an_empty_clipboard() -> None:
    targets_process = _fake_process(stdout=b"UTF8_STRING\nSTRING\n")
    read_process = _fake_process(stdout=b"")

    with (
        patch(
            "agenthub.clipboard.resolve_clipboard_command",
            return_value=("xclip", "-selection", "clipboard", "-o"),
        ),
        patch(
            "agenthub.clipboard.asyncio.create_subprocess_exec",
            AsyncMock(side_effect=[targets_process, read_process]),
        ),
    ):
        assert await clipboard.read_clipboard_text() == ""


async def test_read_returns_none_when_the_command_fails() -> None:
    process = _fake_process(returncode=1)

    with (
        patch(
            "agenthub.clipboard.resolve_clipboard_command",
            return_value=("xsel", "--clipboard", "--output"),
        ),
        patch(
            "agenthub.clipboard.asyncio.create_subprocess_exec",
            AsyncMock(return_value=process),
        ),
    ):
        assert await clipboard.read_clipboard_text() is None


async def test_read_returns_none_when_the_backend_cannot_spawn() -> None:
    with (
        patch(
            "agenthub.clipboard.resolve_clipboard_command",
            return_value=("wl-paste", "--no-newline"),
        ),
        patch(
            "agenthub.clipboard.asyncio.create_subprocess_exec",
            AsyncMock(side_effect=OSError("executable vanished")),
        ),
    ):
        assert await clipboard.read_clipboard_text() is None


async def test_read_returns_none_for_non_utf8_clipboard_bytes() -> None:
    process = _fake_process(stdout=b"\x89PNG\r\n\x1a\n")

    with (
        patch(
            "agenthub.clipboard.resolve_clipboard_command",
            return_value=("xsel", "--clipboard", "--output"),
        ),
        patch(
            "agenthub.clipboard.asyncio.create_subprocess_exec",
            AsyncMock(return_value=process),
        ),
    ):
        content = await clipboard.read_clipboard()
        assert content.kind == clipboard.ClipboardKind.NON_TEXT
        assert await clipboard.read_clipboard_text() is None


async def test_read_times_out_and_kills_the_reader(monkeypatch) -> None:
    monkeypatch.setattr(clipboard, "_READ_TIMEOUT_SECONDS", 0.01)
    process = Mock()
    process.kill = Mock()
    process.wait = AsyncMock(return_value=0)

    async def hang() -> tuple[bytes, bytes]:
        await asyncio.sleep(5)
        return b"", b""

    process.communicate = hang

    with (
        patch(
            "agenthub.clipboard.resolve_clipboard_command",
            return_value=("wl-paste", "--no-newline"),
        ),
        patch(
            "agenthub.clipboard.asyncio.create_subprocess_exec",
            AsyncMock(return_value=process),
        ),
    ):
        assert await clipboard.read_clipboard_text() is None

    process.kill.assert_called_once_with()


async def test_cancelling_a_read_kills_and_awaits_the_reader() -> None:
    process = Mock()
    process.returncode = None
    process.kill = Mock()
    process.wait = AsyncMock(return_value=-9)

    async def hang() -> tuple[bytes, bytes]:
        await asyncio.Event().wait()
        return b"", b""

    process.communicate = hang

    with (
        patch(
            "agenthub.clipboard.resolve_clipboard_command",
            return_value=("wl-paste", "--no-newline"),
        ),
        patch(
            "agenthub.clipboard.asyncio.create_subprocess_exec",
            AsyncMock(return_value=process),
        ),
    ):
        read_task = asyncio.create_task(clipboard.read_clipboard_text())
        await asyncio.sleep(0)
        read_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await read_task

    process.kill.assert_called_once_with()
    process.wait.assert_awaited_once_with()
