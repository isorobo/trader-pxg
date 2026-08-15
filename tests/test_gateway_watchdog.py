"""Gateway watchdog tests: one alert per outage, all-clear on recovery,
internal failures never masquerade as outages."""

from __future__ import annotations

import pytest

from trader.paper import gateway_watchdog


@pytest.fixture(autouse=True)
def _isolated_state(tmp_path, monkeypatch):
    monkeypatch.setattr(gateway_watchdog, "_STATE_PATH", tmp_path / "wd.state")


@pytest.fixture
def sent(monkeypatch):
    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(
        gateway_watchdog.alerts, "notify", lambda t, m: calls.append((t, m))
    )
    return calls


def test_alert_says_logged_out_when_process_alive(monkeypatch, sent):
    """2026-08-16: the two outage kinds need OPPOSITE fixes, so the alert
    must name which one it is."""
    monkeypatch.setattr(gateway_watchdog, "probe_port", lambda *a, **k: False)
    monkeypatch.setattr(gateway_watchdog, "gateway_process_alive", lambda: True)

    gateway_watchdog.run_watchdog_once()

    assert "logged the session out" in sent[0][1]


def test_alert_says_process_gone_when_not_running(monkeypatch, sent):
    monkeypatch.setattr(gateway_watchdog, "probe_port", lambda *a, **k: False)
    monkeypatch.setattr(gateway_watchdog, "gateway_process_alive", lambda: False)

    gateway_watchdog.run_watchdog_once()

    assert "NOT running at all" in sent[0][1]


def test_down_alerts_once_then_stays_quiet(monkeypatch, sent):
    monkeypatch.setattr(gateway_watchdog, "probe_port", lambda *a, **k: False)
    monkeypatch.setattr(gateway_watchdog, "gateway_process_alive", lambda: True)

    gateway_watchdog.run_watchdog_once()
    gateway_watchdog.run_watchdog_once()
    gateway_watchdog.run_watchdog_once()

    assert len(sent) == 1
    assert "GATEWAY DOWN" in sent[0][1]


def test_recovery_sends_all_clear_and_rearms(monkeypatch, sent):
    up = {"v": False}
    monkeypatch.setattr(gateway_watchdog, "probe_port", lambda *a, **k: up["v"])

    gateway_watchdog.run_watchdog_once()  # down -> alert 1
    up["v"] = True
    gateway_watchdog.run_watchdog_once()  # recovery -> all-clear
    up["v"] = False
    gateway_watchdog.run_watchdog_once()  # down again -> alert 2

    assert len(sent) == 3
    assert "GATEWAY DOWN" in sent[0][1]
    assert "recovered" in sent[1][1]
    assert "GATEWAY DOWN" in sent[2][1]


def test_healthy_runs_send_nothing(monkeypatch, sent):
    monkeypatch.setattr(gateway_watchdog, "probe_port", lambda *a, **k: True)

    gateway_watchdog.run_watchdog_once()
    gateway_watchdog.run_watchdog_once()

    assert sent == []


def test_internal_failure_exits_zero_and_never_alerts(monkeypatch, sent, capsys):
    monkeypatch.setattr(
        gateway_watchdog,
        "run_watchdog_once",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    logged = []
    monkeypatch.setattr(
        gateway_watchdog.ops_log,
        "append_ops_log",
        lambda t, m: logged.append((t, m)),
    )

    with pytest.raises(SystemExit) as excinfo:
        gateway_watchdog.main(["--once"])

    assert excinfo.value.code == 0
    assert sent == []
    assert logged and "internal failure" in logged[0][1]
