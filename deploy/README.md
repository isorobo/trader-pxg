# VPS deployment — ending the missed-night problem

**Why this exists.** Eight of the first twelve live nights recorded nothing,
and the 2026-08-14 trading night was lost to a 29-hour Gateway outage. Every
one of those failures had the same root cause: the system runs on a desktop
that sleeps, gets closed, and logs out. A VPS does none of those things.

## What you need to buy

| Spec | Why |
|---|---|
| 2 vCPU, **4 GB RAM**, 40 GB disk | IB Gateway is a Java desktop app and wants ~1.5–2 GB on its own; the rest runs the Python jobs |
| Ubuntu 24.04 LTS | What these scripts target |
| US East region | Closest to IBKR's servers (latency is irrelevant for daily bars, but it costs nothing to be near) |

Roughly **$5–24/month** depending on provider. Hetzner CX22 is the value pick
at about €4.50; DigitalOcean/Vultr are ~$24 for the same specs with a
friendlier console.

## Stage 1 — everything that needs no broker (do this first)

Gets the scanner, crypto leg, snipe experiment, tournament and daily digest
running 24/7. No Gateway, no GUI, low risk.

```bash
ssh root@<VPS_IP>
apt-get update && apt-get install -y git
git clone https://github.com/isorobo/trader-pxg.git /tmp/t
bash /tmp/t/deploy/setup_vps.sh
```

Then copy the two things the repo deliberately does not contain:

```bash
scp .env          trader@<VPS_IP>:/home/trader/trader/.env
scp data/trader.db trader@<VPS_IP>:/home/trader/trader/data/trader.db
```

`.env` holds the Telegram and API credentials; `trader.db` carries the trade
history so the ledger continues rather than restarting from zero.

## Stage 2 — the stock book (IB Gateway headless)

```bash
IBKR_USER=<paper username> IBKR_PASS=<paper password> \
  bash /home/trader/trader/deploy/setup_gateway.sh
```

This installs a virtual display (Xvfb) plus IBC, which logs the Gateway in
automatically and restarts it after IBKR's daily forced logout — the failure
that has cost the most trading nights. It then enables the broker-dependent
timers (reconcile, guardian, watchdog, entry scan).

## Verifying it works

```bash
systemctl list-timers 'trader-*'      # next run times for all nine jobs
journalctl -u trader-paper-entry -n 50 # what last night's scan did
systemctl status ibgateway             # broker connection health
```

The real proof is your phone: fills, the Gateway watchdog alarm, and the
08:30 daily P&L digest all keep arriving exactly as they do now.

## Switching over cleanly

Run both for a day or two, then **disable the Windows tasks** so the two
machines cannot trade the same account twice:

```powershell
foreach ($t in (schtasks /Query /FO CSV | Select-String "Trader")) { ... /Change /DISABLE }
```

Keep the home PC's Gateway logged out once the VPS owns the account —
two Gateways on one paper account will fight over the API session.

## What stays on your machine

Nothing has to. The repo, the ledger, and every job move across. Backtests
and sweeps can run in either place; they only read cached bars.
