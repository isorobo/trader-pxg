#!/usr/bin/env bash
# Stage 2: IB Gateway on a headless VPS, with automatic login.
#
# The Gateway is a Java DESKTOP app -- it has no headless mode. Two pieces
# make it work on a server:
#   Xvfb  -- a virtual screen for it to draw on that nobody looks at
#   IBC   -- types the credentials in, and restarts it after IBKR's
#            periodic forced logout (the exact failure that cost the
#            2026-08-14 trading night, 29h of blindness)
#
# Run AFTER setup_vps.sh, as root:
#   IBKR_USER=youruser IBKR_PASS=yourpass bash setup_gateway.sh

set -euo pipefail

APP_USER="${APP_USER:-trader}"
HOME_DIR="/home/${APP_USER}"
IBC_VERSION="${IBC_VERSION:-3.20.0}"
: "${IBKR_USER:?set IBKR_USER (the PAPER username)}"
: "${IBKR_PASS:?set IBKR_PASS (the PAPER password)}"

echo "==> Packages: virtual display + java + unzip"
apt-get update -qq
apt-get install -y -qq xvfb openjdk-17-jre unzip curl x11vnc

echo "==> IB Gateway (stable, offline installer)"
sudo -u "${APP_USER}" curl -fsSL \
  https://download2.interactivebrokers.com/installers/ibgateway/stable-standalone/ibgateway-stable-standalone-linux-x64.sh \
  -o "${HOME_DIR}/ibgw.sh"
chmod +x "${HOME_DIR}/ibgw.sh"
sudo -u "${APP_USER}" bash -c "yes '' | ${HOME_DIR}/ibgw.sh -q -dir ${HOME_DIR}/Jts" || true

echo "==> IBC ${IBC_VERSION}"
sudo -u "${APP_USER}" mkdir -p "${HOME_DIR}/ibc"
sudo -u "${APP_USER}" curl -fsSL \
  "https://github.com/IbcAlpha/IBC/releases/download/${IBC_VERSION}/IBCLinux-${IBC_VERSION}.zip" \
  -o "${HOME_DIR}/ibc.zip"
sudo -u "${APP_USER}" unzip -oq "${HOME_DIR}/ibc.zip" -d "${HOME_DIR}/ibc"
chmod +x "${HOME_DIR}/ibc/"*.sh "${HOME_DIR}/ibc/scripts/"*.sh 2>/dev/null || true

echo "==> IBC config (paper mode, API on 4002, auto-restart)"
sudo -u "${APP_USER}" tee "${HOME_DIR}/ibc/config.ini" >/dev/null <<EOF
IbLoginId=${IBKR_USER}
IbPassword=${IBKR_PASS}
TradingMode=paper
IbDir=${HOME_DIR}/Jts
OverrideTwsApiPort=4002
# Standing rule 6 lives at this layer too: paper mode, paper port, never 4001.
AcceptIncomingConnectionAction=accept
AcceptNonBrokerageAccountWarning=yes
DismissPasswordExpiryWarning=yes
ReadOnlyApi=no
# IBKR forces a session end daily; restart rather than sit dead until a human notices.
ClosedownAt=
AutoRestartOption=RestartDaily
EOF
chmod 600 "${HOME_DIR}/ibc/config.ini"
chown "${APP_USER}:${APP_USER}" "${HOME_DIR}/ibc/config.ini"

echo "==> systemd service: Gateway under a virtual display, always up"
tee /etc/systemd/system/ibgateway.service >/dev/null <<EOF
[Unit]
Description=IB Gateway (headless via Xvfb + IBC)
After=network-online.target
Wants=network-online.target

[Service]
User=${APP_USER}
Environment=DISPLAY=:1
Environment=TWS_MAJOR_VRSN=1030
Environment=IBC_INI=${HOME_DIR}/ibc/config.ini
Environment=IBC_PATH=${HOME_DIR}/ibc
Environment=TWS_PATH=${HOME_DIR}/Jts
ExecStartPre=/usr/bin/pkill -f "Xvfb :1" || /bin/true
ExecStartPre=/bin/bash -c '/usr/bin/Xvfb :1 -screen 0 1024x768x24 & sleep 3'
ExecStart=${HOME_DIR}/ibc/gatewaystart.sh
Restart=always
RestartSec=30

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now ibgateway.service

echo "==> Waiting for port 4002 (up to 3 min)..."
for i in $(seq 1 36); do
  if (echo > /dev/tcp/127.0.0.1/4002) 2>/dev/null; then
    echo "    Gateway API is UP."
    break
  fi
  sleep 5
done

echo "==> Enabling the broker-dependent timers"
for t in trader-reconcile trader-guardian trader-watchdog trader-paper-entry; do
  systemctl enable --now "${t}.timer"
done

cat <<'EOF'

==> Stage 2 done. Checks:
      systemctl status ibgateway
      journalctl -u ibgateway -n 50
      systemctl list-timers 'trader-*'

    If login fails, watch it happen on the virtual screen:
      x11vnc -display :1 -localhost -nopw &   # then SSH-tunnel port 5900

EOF
