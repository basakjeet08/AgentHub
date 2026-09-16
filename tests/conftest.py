"""Shared test harnesses that never launch a real coding agent."""

import sys

import pytest

from agenthub.harnesses import AgentHarness, KeyStroke, ScrollKeys


@pytest.fixture(autouse=True)
def isolate_native_session_discovery(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep tests independent from conversations stored on the host machine."""

    monkeypatch.setattr("agenthub.app.NATIVE_SESSION_ADAPTERS", {})


@pytest.fixture
def sleeping_harness() -> AgentHarness:
    """Return a harness whose harmless child remains alive during UI tests."""

    return AgentHarness(
        id="test-sleeper",
        display_name="Test Sleeper",
        command=(sys.executable, "-c", "import time; time.sleep(30)"),
        scroll=ScrollKeys(
            down=KeyStroke("e", ctrl=True, alt=True),
            up=KeyStroke("y", ctrl=True, alt=True),
        ),
    )
