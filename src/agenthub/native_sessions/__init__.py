"""Provider-specific discovery and exact native conversation resumption."""

from .adapter import (
    NativeSessionAdapter,
    NativeSessionDiscoveryError,
    NativeSessionError,
    NativeSessionResumeError,
)
from .model import LaunchSpec, NativeSession
from .registry import NATIVE_SESSION_ADAPTERS

__all__ = [
    "NATIVE_SESSION_ADAPTERS",
    "LaunchSpec",
    "NativeSession",
    "NativeSessionAdapter",
    "NativeSessionDiscoveryError",
    "NativeSessionError",
    "NativeSessionResumeError",
]
