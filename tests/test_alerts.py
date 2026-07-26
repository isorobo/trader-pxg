"""Tests for trader.paper.alerts and trader.paper.ops_log (05-02-PLAN.md,
Task 2): Telegram fire-and-forget alerts, the rotating ops log, and the
ops_log CLI producer for scheduled_auth/manual_restart_required entries
(BLOCKER 2).

No test performs a real network call -- requests.post is always mocked.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
import requests

from trader.paper import alerts, ops_log

FAKE_TOKEN = "123456:AAFakeTokenValueForTestingOnly"
FAKE_CHAT_ID = "chat-42"


# ---------------------------------------------------------------------------
# send_telegram_alert
# ---------------------------------------------------------------------------


def test_send_telegram_alert_returns_true_on_200():
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    with patch("trader.paper.alerts.requests.post", return_value=mock_response) as mock_post:
        result = alerts.send_telegram_alert(FAKE_TOKEN, FAKE_CHAT_ID, "hello")
    assert result is True
    mock_post.assert_called_once()
    called_url = mock_post.call_args[0][0]
    assert called_url == f"https://api.telegram.org/bot{FAKE_TOKEN}/sendMessage"


def test_send_telegram_alert_returns_false_and_never_raises_on_timeout():
    with patch(
        "trader.paper.alerts.requests.post",
        side_effect=requests.exceptions.Timeout("timed out"),
    ):
        result = alerts.send_telegram_alert(FAKE_TOKEN, FAKE_CHAT_ID, "hello")
    assert result is False


def test_failed_send_never_logs_the_token(caplog):
    with patch(
        "trader.paper.alerts.requests.post",
        side_effect=requests.exceptions.Timeout("timed out"),
    ):
        with caplog.at_level("WARNING"):
            alerts.send_telegram_alert(FAKE_TOKEN, FAKE_CHAT_ID, "hello")
    assert FAKE_TOKEN not in caplog.text
    assert FAKE_CHAT_ID not in caplog.text


def test_failed_send_via_http_error_never_logs_the_token(caplog):
    # raise_for_status()'s own HTTPError message embeds the request URL
    # (which contains the token) -- confirm the log line never surfaces it
    # even in this worse-case path (T-05-02).
    mock_response = MagicMock()
    mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError(
        f"404 Client Error: Not Found for url: https://api.telegram.org/bot{FAKE_TOKEN}/sendMessage"
    )
    with patch("trader.paper.alerts.requests.post", return_value=mock_response):
        with caplog.at_level("WARNING"):
            result = alerts.send_telegram_alert(FAKE_TOKEN, FAKE_CHAT_ID, "hello")
    assert result is False
    assert FAKE_TOKEN not in caplog.text


# ---------------------------------------------------------------------------
# notify
# ---------------------------------------------------------------------------


def test_notify_falls_back_to_ops_log_when_token_unset(tmp_path, monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    log_path = str(tmp_path / "paper_trading.log")

    with patch(
        "trader.paper.ops_log.append_ops_log", wraps=lambda *a, **k: None
    ) as mock_append:
        result = alerts.notify("fill", "AAPL filled at 190.00")

    assert result is False
    mock_append.assert_called_once_with("fill", "AAPL filled at 190.00")


def test_notify_always_appends_ops_log_even_when_telegram_configured(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", FAKE_TOKEN)
    monkeypatch.setenv("TELEGRAM_CHAT_ID", FAKE_CHAT_ID)

    with patch("trader.paper.alerts.send_telegram_alert", return_value=True) as mock_send:
        with patch("trader.paper.ops_log.append_ops_log") as mock_append:
            result = alerts.notify("fill", "AAPL filled at 190.00")

    assert result is True
    mock_send.assert_called_once_with(FAKE_TOKEN, FAKE_CHAT_ID, "AAPL filled at 190.00")
    mock_append.assert_called_once_with("fill", "AAPL filled at 190.00")


# ---------------------------------------------------------------------------
# append_ops_log / compute_run_coverage
# ---------------------------------------------------------------------------


def test_append_ops_log_rejects_unknown_entry_type(tmp_path):
    log_path = str(tmp_path / "paper_trading.log")
    with pytest.raises(ValueError):
        ops_log.append_ops_log("not_a_real_type", "x", log_path=log_path)


def test_scheduled_auth_distinct_from_manual_restart_required(tmp_path):
    log_path = str(tmp_path / "paper_trading.log")
    ops_log.append_ops_log("scheduled_auth", "weekly IBKR 2FA tap, D-13", log_path=log_path)
    ops_log.append_ops_log("manual_restart_required", "cleared breaker after halt", log_path=log_path)

    lines = [
        line for line in open(log_path, encoding="utf-8").read().splitlines() if line
    ]
    assert len(lines) == 2
    entry_types = [line.split("|", 2)[1] for line in lines]
    assert entry_types == ["scheduled_auth", "manual_restart_required"]
    assert "scheduled_auth" in entry_types
    assert "manual_restart_required" in entry_types


def test_compute_run_coverage_never_counts_scheduled_auth_as_a_run(tmp_path):
    log_path = str(tmp_path / "paper_trading.log")
    window_start = datetime(2026, 7, 20, tzinfo=timezone.utc)
    window_end = datetime(2026, 7, 21, tzinfo=timezone.utc)

    # A scheduled_auth entry inside the window must never inflate the
    # scheduled_run coverage tally (the whole point of the distinct type).
    mid = window_start + timedelta(hours=1)
    with patch("trader.paper.ops_log.datetime") as mock_dt:
        mock_dt.now.return_value = mid
        mock_dt.fromisoformat = datetime.fromisoformat
        ops_log.append_ops_log("scheduled_auth", "weekly IBKR 2FA tap, D-13", log_path=log_path)

    coverage = ops_log.compute_run_coverage(
        log_path, window_start, window_end, expected_cadence_minutes=60
    )
    assert coverage["completed"] == 0
    assert coverage["expected"] == 24
    assert coverage["pct"] == 0.0


def test_compute_run_coverage_counts_scheduled_run_entries_in_window(tmp_path):
    log_path = str(tmp_path / "paper_trading.log")
    window_start = datetime(2026, 7, 20, tzinfo=timezone.utc)
    window_end = datetime(2026, 7, 21, tzinfo=timezone.utc)
    mid = window_start + timedelta(hours=1)

    with patch("trader.paper.ops_log.datetime") as mock_dt:
        mock_dt.now.return_value = mid
        mock_dt.fromisoformat = datetime.fromisoformat
        ops_log.append_ops_log("scheduled_run", "guardian tick", log_path=log_path)

    coverage = ops_log.compute_run_coverage(
        log_path, window_start, window_end, expected_cadence_minutes=60
    )
    assert coverage["completed"] == 1
    assert coverage["expected"] == 24


# ---------------------------------------------------------------------------
# ops_log.main CLI (BLOCKER 2)
# ---------------------------------------------------------------------------


def test_main_appends_exactly_one_scheduled_auth_line(tmp_path, capsys):
    log_path = str(tmp_path / "paper_trading.log")
    ops_log.main(
        [
            "--entry-type",
            "scheduled_auth",
            "--message",
            "weekly 2FA tap",
            "--log-path",
            log_path,
        ]
    )
    lines = [
        line for line in open(log_path, encoding="utf-8").read().splitlines() if line
    ]
    assert len(lines) == 1
    assert "|scheduled_auth|" in lines[0]
    assert "weekly 2FA tap" in lines[0]
    captured = capsys.readouterr()
    assert "scheduled_auth" in captured.out


def test_main_rejects_unknown_entry_type_via_argparse(tmp_path, capsys):
    log_path = str(tmp_path / "paper_trading.log")
    with pytest.raises(SystemExit) as exc_info:
        ops_log.main(
            [
                "--entry-type",
                "not_a_real_type",
                "--message",
                "x",
                "--log-path",
                log_path,
            ]
        )
    assert exc_info.value.code != 0
    captured = capsys.readouterr()
    assert "Traceback" not in captured.err
