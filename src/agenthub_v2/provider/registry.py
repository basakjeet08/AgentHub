"""Registry of built-in coding-agent providers."""

from collections.abc import Callable

from .codex import CodexProvider
from .protocol import Provider

DEFAULT_PROVIDER_FACTORIES: tuple[Callable[[], Provider], ...] = (CodexProvider,)
