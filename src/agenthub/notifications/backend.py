"""Best-effort desktop notification delivery backends."""

from __future__ import annotations

import asyncio
import shutil
import sys
from collections.abc import Awaitable
from pathlib import Path
from typing import Protocol

from .model import DesktopNotification

_COMMAND_TIMEOUT_SECONDS = 5
_SOUND_PATHS = (
    Path("/usr/share/sounds/freedesktop/stereo/message-new-instant.oga"),
    Path("/usr/share/sounds/freedesktop/stereo/complete.oga"),
)


class DesktopNotificationBackend(Protocol):
    """Deliver desktop attention without participating in session state."""

    def send(self, notification: DesktopNotification) -> Awaitable[None]:
        """Deliver one notification and its sound."""


class NullDesktopNotificationBackend:
    """Ignore notifications on platforms without a supported backend."""

    async def send(self, notification: DesktopNotification) -> None:
        """Discard one unsupported notification."""


class LinuxDesktopNotificationBackend:
    """Deliver Linux notifications through freedesktop command-line clients."""

    def __init__(
        self,
        *,
        notification_command: tuple[str, ...] | None,
        sound_command: tuple[str, ...] | None,
    ) -> None:
        self._notification_command = notification_command
        self._sound_command = sound_command

    async def send(self, notification: DesktopNotification) -> None:
        """Show the notification and play its standard theme sound independently."""

        commands: list[tuple[str, ...]] = []
        if self._notification_command is not None:
            commands.append(
                (
                    *self._notification_command,
                    "--app-name=AgentHub",
                    "--icon=dialog-information",
                    "--hint=boolean:suppress-sound:true",
                    notification.title,
                    notification.message,
                )
            )
        if self._sound_command is not None:
            commands.append(self._sound_command)
        if commands:
            await asyncio.gather(
                *(_run_command_best_effort(command) for command in commands),
                return_exceptions=True,
            )


async def _run_command_best_effort(command: tuple[str, ...]) -> None:
    """Run one short desktop command without surfacing any failure."""

    process: asyncio.subprocess.Process | None = None
    try:
        process = await asyncio.create_subprocess_exec(
            *command,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await asyncio.wait_for(process.wait(), timeout=_COMMAND_TIMEOUT_SECONDS)
    except TimeoutError:
        if process is not None and process.returncode is None:
            process.kill()
            await process.wait()
    except asyncio.CancelledError:
        if process is not None and process.returncode is None:
            process.kill()
            await process.wait()
        raise
    except OSError:
        return


def _linux_sound_command() -> tuple[str, ...] | None:
    """Resolve a standard freedesktop notification sound player."""

    canberra = shutil.which("canberra-gtk-play")
    if canberra is not None:
        return (
            canberra,
            "--id=message-new-instant",
            "--description=AgentHub activity notification",
        )

    sound_path = next((path for path in _SOUND_PATHS if path.is_file()), None)
    if sound_path is None:
        return None
    for player_name in ("paplay", "pw-play"):
        player = shutil.which(player_name)
        if player is not None:
            return (player, str(sound_path))
    return None


def create_desktop_notification_backend() -> DesktopNotificationBackend:
    """Return the supported backend for the current desktop platform."""

    if not sys.platform.startswith("linux"):
        return NullDesktopNotificationBackend()
    notify_send = shutil.which("notify-send")
    return LinuxDesktopNotificationBackend(
        notification_command=(notify_send,) if notify_send is not None else None,
        sound_command=_linux_sound_command(),
    )
