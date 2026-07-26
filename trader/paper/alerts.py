"""Telegram fire-and-forget alert sender + local-log fallback (D-11).

Alert failure must never block trading logic: send_telegram_alert catches
every Exception, always returns bool, never raises (D-11). Mirrors
trader/ground_truth/report.py's fetch_crypto_close convention -- log only
the failure's type, never the secret itself (T-00-08 precedent, T-05-02
here).
"""

import logging
import os

import requests
from dotenv import load_dotenv

from trader.paper import config, ops_log

log = logging.getLogger(__name__)

TELEGRAM_API_URL = "https://api.telegram.org/bot{token}/sendMessage"


def send_telegram_alert(token: str, chat_id: str, text: str) -> bool:
    """Fire-and-forget: never raises.

    Returns False on any failure (timeout, connection error, non-2xx
    response) and logs only type(error).__name__ and the alert text --
    never the token or chat_id (T-05-02, standing rule 3) -- so a failure
    never leaks the bearer token into a log line, even via an HTTPError's
    own message (which would otherwise embed the request URL).
    """
    try:
        response = requests.post(
            TELEGRAM_API_URL.format(token=token),
            json={"chat_id": chat_id, "text": text},
            timeout=5,
        )
        response.raise_for_status()
        return True
    except Exception as error:
        log.warning(
            "Telegram alert failed (%s): %s", type(error).__name__, text
        )
        return False


def notify(entry_type: str, message: str) -> bool:
    """Send a Telegram alert if configured; always durably append to the
    ops log regardless of Telegram's outcome (D-12's source of truth).

    Never raises: if TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID are unset (not
    configured yet, or before the 05-08 human checkpoint runs), falls back
    to the ops log alone and returns False -- D-11's "alert failure never
    blocks trading logic" applies to the "not configured yet" case too.
    """
    load_dotenv()
    token = os.environ.get(config.TELEGRAM_BOT_TOKEN_ENV)
    chat_id = os.environ.get(config.TELEGRAM_CHAT_ID_ENV)

    if not token or not chat_id:
        ops_log.append_ops_log(entry_type, message)
        return False

    sent = send_telegram_alert(token, chat_id, message)
    # The ops log is the durable source of truth even when Telegram is
    # reachable -- always append, independent of the Telegram result.
    ops_log.append_ops_log(entry_type, message)
    return sent
