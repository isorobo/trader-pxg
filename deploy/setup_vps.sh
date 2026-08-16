#!/usr/bin/env bash
# One-command setup for a fresh Ubuntu 24.04 VPS (owner directive
# 2026-08-16: end the missed-night problem permanently).
#
# Solves the root cause of every lost trading night so far: a home PC that
# sleeps and a Gateway that gets closed. A VPS never sleeps.
#
# Usage (as root on a fresh box):
#   bash setup_vps.sh
#
# Stage 1 (this script) brings up EVERYTHING THAT NEEDS NO BROKER GUI:
# the ground-truth scanner, the crypto leg, the snipe experiment, the
# tournament, and the daily digest. Stage 2 (setup_gateway.sh) adds the
# IB Gateway under a virtual display for the stock book.

set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/isorobo/trader-pxg.git}"
APP_USER="${APP_USER:-trader}"
APP_DIR="/home/${APP_USER}/trader"
TZ_NAME="${TZ_NAME:-Pacific/Auckland}"

echo "==> Timezone -> ${TZ_NAME} (keeps every schedule identical to the home box)"
timedatectl set-timezone "${TZ_NAME}"

echo "==> Base packages"
apt-get update -qq
apt-get install -y -qq python3 python3-venv python3-pip git sqlite3 curl unzip

echo "==> Service user ${APP_USER}"
id -u "${APP_USER}" &>/dev/null || useradd -m -s /bin/bash "${APP_USER}"

echo "==> Clone/update repo at ${APP_DIR}"
if [ -d "${APP_DIR}/.git" ]; then
  sudo -u "${APP_USER}" git -C "${APP_DIR}" pull --ff-only
else
  sudo -u "${APP_USER}" git clone "${REPO_URL}" "${APP_DIR}"
fi

echo "==> Python venv + dependencies"
sudo -u "${APP_USER}" python3 -m venv "${APP_DIR}/.venv"
sudo -u "${APP_USER}" "${APP_DIR}/.venv/bin/pip" install -q --upgrade pip
if [ -f "${APP_DIR}/requirements.txt" ]; then
  sudo -u "${APP_USER}" "${APP_DIR}/.venv/bin/pip" install -q -r "${APP_DIR}/requirements.txt"
else
  sudo -u "${APP_USER}" "${APP_DIR}/.venv/bin/pip" install -q \
    pandas numpy pandas_market_calendars ib_async ccxt yfinance requests python-dotenv pytest hypothesis
fi

echo "==> Directories the app expects"
sudo -u "${APP_USER}" mkdir -p "${APP_DIR}/data" "${APP_DIR}/ops" "${APP_DIR}/reports" "${APP_DIR}/logs"

echo "==> systemd units"
cp "${APP_DIR}/deploy/systemd/"*.service "${APP_DIR}/deploy/systemd/"*.timer /etc/systemd/system/
systemctl daemon-reload

echo "==> Enabling Stage-1 timers (no broker GUI required)"
for t in trader-poll trader-crypto-entry trader-snipe trader-tournament trader-digest; do
  systemctl enable --now "${t}.timer"
done

cat <<'EOF'

==> Stage 1 is LIVE. Still to do, in order:

  1. Copy your secrets across (nothing works without them):
       scp .env trader@<VPS_IP>:/home/trader/trader/.env

  2. Copy your existing ledger so history carries over:
       scp data/trader.db trader@<VPS_IP>:/home/trader/trader/data/trader.db

  3. Stock book (needs the broker GUI): run  bash deploy/setup_gateway.sh

  4. Watch it work:
       systemctl list-timers 'trader-*'
       journalctl -u trader-crypto-entry -f

EOF
