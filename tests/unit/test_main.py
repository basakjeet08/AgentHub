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

    monkeypatch.setattr("agenthub.main.ACTIVITY_ADAPTERS", {"codex": type("Adapter", (), {"run_hook": lambda _self, _event=None: fake_hook()})()})

    exit_code = main(["activity-hook", "codex"])

    assert exit_code == 0
    assert calls == 1


def test_main_routes_devin_activity_hook(monkeypatch) -> None:
    calls = 0

    def fake_hook() -> int:
        nonlocal calls
        calls += 1
        return 0

    monkeypatch.setattr("agenthub.main.ACTIVITY_ADAPTERS", {"devin": type("Adapter", (), {"run_hook": lambda _self, _event=None: fake_hook()})()})

    exit_code = main(["activity-hook", "devin"])

    assert exit_code == 0
    assert calls == 1


def test_main_routes_antigravity_activity_hook(monkeypatch) -> None:
    events = []

    def fake_hook(event_name: str) -> int:
        events.append(event_name)
        return 0

    monkeypatch.setattr("agenthub.main.ACTIVITY_ADAPTERS", {"antigravity": type("Adapter", (), {"run_hook": lambda _self, event=None: fake_hook(event)})()})

    exit_code = main(["activity-hook", "antigravity", "PreInvocation"])

    assert exit_code == 0
    assert events == ["PreInvocation"]


def test_main_rejects_malformed_provider_hook_arguments() -> None:
    import pytest

    with pytest.raises(SystemExit):
        main(["activity-hook", "codex", "unexpected-event"])

    with pytest.raises(SystemExit):
        main(["activity-hook", "antigravity"])
