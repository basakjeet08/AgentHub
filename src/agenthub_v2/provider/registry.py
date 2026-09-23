"""Registry of built-in coding-agent providers."""

from collections.abc import Callable

from .antigravity import AntigravityProvider
from .codex import CodexProvider
from .devin import DevinProvider
from .opencode import OpenCodeProvider
from .protocol import Provider

DEFAULT_PROVIDER_FACTORIES: tuple[Callable[[], Provider], ...] = (
    AntigravityProvider,
    CodexProvider,
    DevinProvider,
    OpenCodeProvider,
)
