"""Gateway watchdog (owner max-list item 2, 2026-08-13): the silent-outage
killer. 8 of the first 12 live nights were lost to a dead Gateway or a
sleeping machine, discovered DAYS later -- this watchdog makes an outage
loud within 15 minutes instead.

Every scheduled run probes the IBKR API port (4002). On a DOWN result it
sends ONE Telegram alert per outage (a state file dedupes -- no hourly
nagging), and on recovery it sends the all-clear and resets. The probe is
a plain TCP connect: no API session, no client id consumed, safe beside
the trading processes.

Never raises to the scheduler: any internal error logs to the ops log and
exits 0 -- a broken watchdog must not LOOK like a broken Gateway.
"""

from __future__ import annotations

import argparse
import socket
import sys
from pathlib import Path

from trader.paper import alerts, config, ops_log

_STATE_PATH = Path("ops/gateway_watchdog.state")


def probe_port(host: str, port: int, timeout_s: float = 5.0) -> bool:
    """True when a TCP connection to the Gateway's API port succeeds."""
    try:
        with socket.create_connection((host, port), timeout=timeout_s):
            return True
    except OSError:
        return False


def _read_state() -> str:
    try:
        return _STATE_PATH.read_text(encoding="utf-8").strip()
    except OSError:
        return "up"  # first run / missing file: assume healthy


def _write_state(state: str) -> None:
    _STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _STATE_PATH.write_text(state, encoding="utf-8")


def run_watchdog_once(host: str | None = None, port: int | None = None) -> dict:
    host = host if host is not None else config.ibkr_host()
    port = port if port is not None else config.IBKR_PAPER_PORT

    up_now = probe_port(host, port)
    prior = _read_state()

    if not up_now and prior != "down":
        alerts.notify(
            "error",
            "GATEWAY DOWN: IBKR Gateway port "
            f"{port} is not answering -- stock entries, exits, and "
            "reconciliation are BLIND until you open the Gateway and click "
            "Paper Log In. (One alert per outage; the all-clear follows on "
            "recovery.)",
        )
        _write_state("down")
    elif up_now and prior == "down":
        alerts.notify(
            "heartbeat",
            f"Gateway recovered: port {port} answering again -- trading "
            "loops resume on their own schedules.",
        )
        _write_state("up")
    else:
        _write_state("up" if up_now else "down")

    return {"up": up_now, "prior": prior}


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="python -m trader.paper.gateway_watchdog",
        description="Probe the IBKR Gateway port; Telegram once per outage/recovery.",
    )
    parser.add_argument("--once", action="store_true", required=True)
    parser.parse_args(argv)

    try:
        print(run_watchdog_once())
    except Exception as error:  # noqa: BLE001 -- watchdog must never look like the outage
        try:
            ops_log.append_ops_log(
                "error", f"gateway watchdog internal failure: {type(error).__name__}: {error}"
            )
        except Exception:
            pass
        print({"watchdog_error": str(error)})
    sys.exit(0)


if __name__ == "__main__":
    main()
