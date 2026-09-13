"""Tests for the installed command's bootstrap function."""

from agenthub.main import main


def test_main_runs_the_application(monkeypatch) -> None:
    calls = 0

    def fake_run(_app) -> None:
        nonlocal calls
        calls += 1

    monkeypatch.setattr("agenthub.main.AgentHubApp.run", fake_run)

    main()

    assert calls == 1
