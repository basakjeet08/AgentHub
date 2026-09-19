"""Tests for the installed command's bootstrap function."""

from agenthub.main import main


def test_main_runs_the_application(monkeypatch) -> None:
    calls = 0

    def fake_run(_app) -> None:
        nonlocal calls
        calls += 1

    monkeypatch.setattr("agenthub.app.AgentHubApp.run", fake_run)

    main([])

    assert calls == 1


def test_main_routes_codex_activity_hook(monkeypatch) -> None:
    calls = 0

    def fake_hook() -> int:
        nonlocal calls
        calls += 1
        return 0

    monkeypatch.setattr("agenthub.main.run_codex_activity_hook", fake_hook)

    exit_code = main(["activity-hook", "codex"])

    assert exit_code == 0
    assert calls == 1


def test_main_routes_devin_activity_hook(monkeypatch) -> None:
    calls = 0

    def fake_hook() -> int:
        nonlocal calls
        calls += 1
        return 0

    monkeypatch.setattr("agenthub.main.run_devin_activity_hook", fake_hook)

    exit_code = main(["activity-hook", "devin"])

    assert exit_code == 0
    assert calls == 1
