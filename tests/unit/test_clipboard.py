"""Unit coverage for the platform-oriented system clipboard boundary."""

import asyncio
from dataclasses import FrozenInstanceError
from unittest.mock import AsyncMock, Mock, patch

import pytest

from agenthub.clipboard import ClipboardContent, ClipboardKind, ClipboardService
from agenthub.clipboard.backends import (
    LinuxClipboardBackend,
    MacOSClipboardBackend,
    create_clipboard_backend,
)
from agenthub.clipboard.backends import linux as linux_backend
from agenthub.clipboard.backends import macos as macos_backend


def _fake_process(stdout: bytes = b"", stderr: bytes = b"", returncode: int = 0) -> Mock:
    process = Mock()
    process.communicate = AsyncMock(return_value=(stdout, stderr))
    process.returncode = returncode
    process.kill = Mock()
    process.wait = AsyncMock(return_value=returncode)
    return process


def test_clipboard_content_is_immutable() -> None:
    content = ClipboardContent(ClipboardKind.TEXT, "hello")

    with pytest.raises(FrozenInstanceError):
        content.text = "changed"  # type: ignore[misc]


def test_factory_selects_linux_backend() -> None:
    with patch("agenthub.clipboard.backends.factory.sys.platform", "linux"):
        assert isinstance(create_clipboard_backend(), LinuxClipboardBackend)


def test_factory_selects_macos_backend() -> None:
    with patch("agenthub.clipboard.backends.factory.sys.platform", "darwin"):
        assert isinstance(create_clipboard_backend(), MacOSClipboardBackend)


def test_factory_returns_none_for_an_unsupported_platform() -> None:
    with patch("agenthub.clipboard.backends.factory.sys.platform", "win32"):
        assert create_clipboard_backend() is None


def test_wayland_prefers_wl_paste_text() -> None:
    with (
        patch.dict("os.environ", {"WAYLAND_DISPLAY": "wayland-1", "DISPLAY": ""}),
        patch(
            "agenthub.clipboard.backends.linux.shutil.which",
            return_value="/usr/bin/wl-paste",
        ),
    ):
        assert linux_backend._resolve_clipboard_command() == (
            "wl-paste",
            "--no-newline",
        )


def test_wayland_resolves_wl_paste_list_types() -> None:
    assert linux_backend._resolve_clipboard_targets_command(
        ("wl-paste", "--no-newline")
    ) == ("wl-paste", "--list-types")


def test_wayland_without_wl_paste_falls_back_to_xclip() -> None:
    with (
        patch.dict("os.environ", {"WAYLAND_DISPLAY": "wayland-1", "DISPLAY": ":0"}),
        patch(
            "agenthub.clipboard.backends.linux.shutil.which",
            side_effect=lambda name: "/usr/bin/xclip" if name == "xclip" else None,
        ),
    ):
        assert linux_backend._resolve_clipboard_command() == (
            "xclip",
            "-selection",
            "clipboard",
            "-o",
        )


def test_x11_resolves_xclip_targets() -> None:
    assert linux_backend._resolve_clipboard_targets_command(
        ("xclip", "-selection", "clipboard", "-o")
    ) == (
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
            "agenthub.clipboard.backends.linux.shutil.which",
            side_effect=lambda name: "/usr/bin/xsel" if name == "xsel" else None,
        ),
    ):
        assert linux_backend._resolve_clipboard_command() == (
            "xsel",
            "--clipboard",
            "--output",
        )


async def test_linux_without_a_command_returns_unavailable() -> None:
    with patch(
        "agenthub.clipboard.backends.linux._resolve_clipboard_command",
        return_value=None,
    ):
        content = await LinuxClipboardBackend().read()

    assert content == ClipboardContent(ClipboardKind.UNAVAILABLE)


async def test_linux_spawns_the_resolved_command_and_decodes_utf8() -> None:
    expected_text = "first line\ncafé 🐟\tCJK: 你好\n"
    targets_process = _fake_process(b"text/plain\nUTF8_STRING\n")
    read_process = _fake_process(expected_text.encode())

    with (
        patch(
            "agenthub.clipboard.backends.linux._resolve_clipboard_command",
            return_value=("wl-paste", "--no-newline"),
        ),
        patch(
            "agenthub.clipboard.backends.linux.asyncio.create_subprocess_exec",
            AsyncMock(side_effect=[targets_process, read_process]),
        ) as spawn,
    ):
        content = await LinuxClipboardBackend().read()

    assert content == ClipboardContent(ClipboardKind.TEXT, expected_text)
    assert spawn.await_count == 2


async def test_xsel_read_skips_target_inspection() -> None:
    expected_text = "first line\ncafé 🐟\n"
    read_process = _fake_process(expected_text.encode())

    with (
        patch(
            "agenthub.clipboard.backends.linux._resolve_clipboard_command",
            return_value=("xsel", "--clipboard", "--output"),
        ),
        patch(
            "agenthub.clipboard.backends.linux.asyncio.create_subprocess_exec",
            AsyncMock(return_value=read_process),
        ) as spawn,
    ):
        content = await LinuxClipboardBackend().read()

    assert content == ClipboardContent(ClipboardKind.TEXT, expected_text)
    spawn.assert_awaited_once_with(
        "xsel",
        "--clipboard",
        "--output",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )


@pytest.mark.parametrize(
    "targets",
    [b"image/png\n", b"image/png\ntext/plain\ntext/html\n"],
)
async def test_wayland_detects_image_types(targets: bytes) -> None:
    process = _fake_process(stdout=targets)

    with (
        patch(
            "agenthub.clipboard.backends.linux._resolve_clipboard_command",
            return_value=("wl-paste", "--no-newline"),
        ),
        patch(
            "agenthub.clipboard.backends.linux.asyncio.create_subprocess_exec",
            AsyncMock(return_value=process),
        ),
    ):
        content = await LinuxClipboardBackend().read()

    assert content == ClipboardContent(ClipboardKind.NON_TEXT)


async def test_wayland_reports_nothing_copied_as_empty() -> None:
    process = _fake_process(stderr=b"Nothing is copied\n", returncode=1)

    with (
        patch(
            "agenthub.clipboard.backends.linux._resolve_clipboard_command",
            return_value=("wl-paste", "--no-newline"),
        ),
        patch(
            "agenthub.clipboard.backends.linux.asyncio.create_subprocess_exec",
            AsyncMock(return_value=process),
        ),
    ):
        content = await LinuxClipboardBackend().read()

    assert content == ClipboardContent(ClipboardKind.EMPTY)


async def test_xclip_detects_image_targets() -> None:
    process = _fake_process(stdout=b"TARGETS\nimage/png\n")

    with (
        patch(
            "agenthub.clipboard.backends.linux._resolve_clipboard_command",
            return_value=("xclip", "-selection", "clipboard", "-o"),
        ),
        patch(
            "agenthub.clipboard.backends.linux.asyncio.create_subprocess_exec",
            AsyncMock(return_value=process),
        ),
    ):
        content = await LinuxClipboardBackend().read()

    assert content == ClipboardContent(ClipboardKind.NON_TEXT)


async def test_linux_empty_payload_returns_empty() -> None:
    targets_process = _fake_process(stdout=b"UTF8_STRING\nSTRING\n")
    read_process = _fake_process(stdout=b"")

    with (
        patch(
            "agenthub.clipboard.backends.linux._resolve_clipboard_command",
            return_value=("xclip", "-selection", "clipboard", "-o"),
        ),
        patch(
            "agenthub.clipboard.backends.linux.asyncio.create_subprocess_exec",
            AsyncMock(side_effect=[targets_process, read_process]),
        ),
    ):
        content = await LinuxClipboardBackend().read()

    assert content == ClipboardContent(ClipboardKind.EMPTY)


async def test_linux_command_failure_returns_unavailable() -> None:
    process = _fake_process(returncode=1)

    with (
        patch(
            "agenthub.clipboard.backends.linux._resolve_clipboard_command",
            return_value=("xsel", "--clipboard", "--output"),
        ),
        patch(
            "agenthub.clipboard.backends.linux.asyncio.create_subprocess_exec",
            AsyncMock(return_value=process),
        ),
    ):
        content = await LinuxClipboardBackend().read()

    assert content == ClipboardContent(ClipboardKind.UNAVAILABLE)


async def test_linux_spawn_failure_returns_unavailable() -> None:
    with (
        patch(
            "agenthub.clipboard.backends.linux._resolve_clipboard_command",
            return_value=("wl-paste", "--no-newline"),
        ),
        patch(
            "agenthub.clipboard.backends.linux.asyncio.create_subprocess_exec",
            AsyncMock(side_effect=OSError("executable vanished")),
        ),
    ):
        content = await LinuxClipboardBackend().read()

    assert content == ClipboardContent(ClipboardKind.UNAVAILABLE)


async def test_linux_invalid_utf8_is_non_text() -> None:
    process = _fake_process(stdout=b"\x89PNG\r\n\x1a\n")

    with (
        patch(
            "agenthub.clipboard.backends.linux._resolve_clipboard_command",
            return_value=("xsel", "--clipboard", "--output"),
        ),
        patch(
            "agenthub.clipboard.backends.linux.asyncio.create_subprocess_exec",
            AsyncMock(return_value=process),
        ),
    ):
        content = await LinuxClipboardBackend().read()

    assert content == ClipboardContent(ClipboardKind.NON_TEXT)


@pytest.mark.parametrize("backend_module", [linux_backend, macos_backend])
async def test_read_timeout_kills_and_reaps_the_reader(
    monkeypatch,
    backend_module,
) -> None:
    monkeypatch.setattr(backend_module, "_READ_TIMEOUT_SECONDS", 0.01)
    process = Mock()
    process.returncode = None
    process.kill = Mock()
    process.wait = AsyncMock(return_value=-9)

    async def hang() -> tuple[bytes, bytes]:
        await asyncio.sleep(5)
        return b"", b""

    process.communicate = hang

    with patch.object(
        backend_module.asyncio,
        "create_subprocess_exec",
        AsyncMock(return_value=process),
    ):
        result = await backend_module._run_command(("clipboard-reader",))

    assert result is None
    process.kill.assert_called_once_with()
    process.wait.assert_awaited_once_with()


@pytest.mark.parametrize("backend_module", [linux_backend, macos_backend])
async def test_cancelling_read_kills_and_reaps_the_reader(backend_module) -> None:
    process = Mock()
    process.returncode = None
    process.kill = Mock()
    process.wait = AsyncMock(return_value=-9)

    async def hang() -> tuple[bytes, bytes]:
        await asyncio.Event().wait()
        return b"", b""

    process.communicate = hang

    with patch.object(
        backend_module.asyncio,
        "create_subprocess_exec",
        AsyncMock(return_value=process),
    ):
        read_task = asyncio.create_task(
            backend_module._run_command(("clipboard-reader",))
        )
        await asyncio.sleep(0)
        read_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await read_task

    process.kill.assert_called_once_with()
    process.wait.assert_awaited_once_with()


async def test_macos_uses_pbpaste_and_decodes_utf8() -> None:
    process = _fake_process(stdout="café".encode())

    with (
        patch(
            "agenthub.clipboard.backends.macos.shutil.which",
            return_value="/usr/bin/pbpaste",
        ),
        patch(
            "agenthub.clipboard.backends.macos.asyncio.create_subprocess_exec",
            AsyncMock(return_value=process),
        ) as spawn,
    ):
        content = await MacOSClipboardBackend().read()

    assert content == ClipboardContent(ClipboardKind.TEXT, "café")
    spawn.assert_awaited_once_with(
        "pbpaste",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )


@pytest.mark.parametrize(
    ("stdout", "returncode", "expected_kind"),
    [
        (b"", 0, ClipboardKind.EMPTY),
        (b"", 1, ClipboardKind.UNAVAILABLE),
        (b"\x89PNG\r\n\x1a\n", 0, ClipboardKind.NON_TEXT),
    ],
)
async def test_macos_classifies_command_results(
    stdout: bytes,
    returncode: int,
    expected_kind: ClipboardKind,
) -> None:
    process = _fake_process(stdout=stdout, returncode=returncode)

    with (
        patch(
            "agenthub.clipboard.backends.macos.shutil.which",
            return_value="/usr/bin/pbpaste",
        ),
        patch(
            "agenthub.clipboard.backends.macos.asyncio.create_subprocess_exec",
            AsyncMock(return_value=process),
        ),
    ):
        content = await MacOSClipboardBackend().read()

    assert content.kind is expected_kind


async def test_macos_missing_command_and_spawn_failure_are_unavailable() -> None:
    with patch("agenthub.clipboard.backends.macos.shutil.which", return_value=None):
        missing = await MacOSClipboardBackend().read()

    with (
        patch(
            "agenthub.clipboard.backends.macos.shutil.which",
            return_value="/usr/bin/pbpaste",
        ),
        patch(
            "agenthub.clipboard.backends.macos.asyncio.create_subprocess_exec",
            AsyncMock(side_effect=OSError("executable vanished")),
        ),
    ):
        spawn_failure = await MacOSClipboardBackend().read()

    assert missing == ClipboardContent(ClipboardKind.UNAVAILABLE)
    assert spawn_failure == ClipboardContent(ClipboardKind.UNAVAILABLE)


async def test_service_uses_an_injected_backend() -> None:
    backend = Mock()
    backend.read = AsyncMock(return_value=ClipboardContent(ClipboardKind.TEXT, "hello"))
    service = ClipboardService(backend)

    assert await service.read() == ClipboardContent(ClipboardKind.TEXT, "hello")
    backend.read.assert_awaited_once_with()


async def test_service_without_a_platform_backend_returns_unavailable() -> None:
    with patch("agenthub.clipboard.service.create_clipboard_backend", return_value=None):
        service = ClipboardService()

    assert await service.read() == ClipboardContent(ClipboardKind.UNAVAILABLE)


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        (ClipboardContent(ClipboardKind.TEXT, "hello"), "hello"),
        (ClipboardContent(ClipboardKind.EMPTY), ""),
        (ClipboardContent(ClipboardKind.NON_TEXT), None),
        (ClipboardContent(ClipboardKind.UNAVAILABLE), None),
    ],
)
async def test_service_text_convenience_mapping(
    content: ClipboardContent,
    expected: str | None,
) -> None:
    backend = Mock()
    backend.read = AsyncMock(return_value=content)

    assert await ClipboardService(backend).read_text() == expected
