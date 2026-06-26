#!/usr/bin/env bash
# install.sh — idempotent deployment script for the production service lab.
# Safe to re-run (re-run to redeploy new code). Uses sudo internally;
# do NOT run as: sudo bash install.sh
#
# Deployment model:
#   - Code is deployed to /opt/ridelab (native disk), separate from the git
#     checkout you edit in. This is more production-like and avoids running
#     services out of a slow/ephemeral VM share.
#   - Services run as a dedicated, unprivileged system account "ridelab"
#     (no login shell, no home) — least privilege, not your login user.
#
# Usage: bash scripts/install.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

DEPLOY_PREFIX="/opt/ridelab"      # where the running code lives
SERVICE_ACCOUNT="ridelab"         # dedicated system account the services run as

step(){ printf '\n\033[1;34m==>\033[0m %s\n' "$1"; }

step "Production Service Lab Installer"
echo "    Repo        : $REPO_ROOT"
echo "    Deploy to   : $DEPLOY_PREFIX"
echo "    Service user: $SERVICE_ACCOUNT (system account)"

# ---------------------------------------------------------------------------
step "1/7  System packages"
# ---------------------------------------------------------------------------
sudo apt-get update -qq
sudo apt-get install -y python3 python3-pip python3-venv nginx curl ufw rsync

# ---------------------------------------------------------------------------
step "2/7  Service discovery (/etc/hosts)"
# ---------------------------------------------------------------------------
for entry in \
    "127.0.0.1   ride-booking.internal" \
    "127.0.0.1   driver-matching.internal" \
    "127.0.0.1   ride-dispatch.internal"
do
    name=$(echo "$entry" | awk '{print $2}')
    if grep -qF "$name" /etc/hosts; then
        echo "    Already exists: $name"
    else
        echo "$entry" | sudo tee -a /etc/hosts > /dev/null
        echo "    Added: $entry"
    fi
done

# ---------------------------------------------------------------------------
step "3/7  Service account + deploy code to $DEPLOY_PREFIX"
# ---------------------------------------------------------------------------
# Dedicated system account: no login, no home directory. '|| true' keeps the
# step idempotent (re-running won't error if it already exists).
sudo useradd --system --no-create-home --shell /usr/sbin/nologin "$SERVICE_ACCOUNT" 2>/dev/null || true

# Deploy only what the services need (code + readiness script + requirements).
sudo mkdir -p "$DEPLOY_PREFIX"
sudo rsync -a --delete --exclude '__pycache__' "$REPO_ROOT/services/" "$DEPLOY_PREFIX/services/"
sudo rsync -a           --exclude '__pycache__' "$REPO_ROOT/scripts/wait-for-deps.sh" "$DEPLOY_PREFIX/scripts/"
sudo cp "$REPO_ROOT/requirements.txt" "$DEPLOY_PREFIX/requirements.txt"

# Virtual environment lives with the deployed code, not in the repo.
sudo python3 -m venv "$DEPLOY_PREFIX/venv"
sudo "$DEPLOY_PREFIX/venv/bin/pip" install -q -r "$DEPLOY_PREFIX/requirements.txt"
sudo chmod +x "$DEPLOY_PREFIX/scripts/wait-for-deps.sh"

# Everything under the deploy prefix is owned by the service account.
sudo chown -R "$SERVICE_ACCOUNT:$SERVICE_ACCOUNT" "$DEPLOY_PREFIX"
echo "    Deployed and owned by $SERVICE_ACCOUNT."

# ---------------------------------------------------------------------------
step "4/7  Systemd service files"
# ---------------------------------------------------------------------------
# Units are self-contained (fixed /opt paths + User=ridelab), so just copy them.
for svc in ride-dispatch driver-matching ride-booking; do
    sudo cp "$REPO_ROOT/systemd/${svc}.service" "/etc/systemd/system/${svc}.service"
    echo "    Installed: /etc/systemd/system/${svc}.service"
done
sudo systemctl daemon-reload

# ---------------------------------------------------------------------------
step "5/7  Nginx"
# ---------------------------------------------------------------------------
sudo cp "$REPO_ROOT/nginx/production-service-lab.conf" \
        /etc/nginx/sites-available/production-service-lab
sudo ln -sf /etc/nginx/sites-available/production-service-lab \
            /etc/nginx/sites-enabled/production-service-lab
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl reload nginx
echo "    Done."

# ---------------------------------------------------------------------------
step "6/7  Firewall"
# ---------------------------------------------------------------------------
if [ "${SKIP_FIREWALL:-0}" != "1" ]; then
    sudo bash "$REPO_ROOT/scripts/setup-firewall.sh"
else
    echo "    Skipped (SKIP_FIREWALL=1)"
fi

# ---------------------------------------------------------------------------
step "7/7  Enable and start services"
# ---------------------------------------------------------------------------
sudo systemctl enable --now ride-dispatch
sudo systemctl enable --now driver-matching
sudo systemctl enable --now ride-booking
sudo systemctl enable nginx
echo "    Done."

# ---------------------------------------------------------------------------
printf '\n\033[1;34m==>\033[0m Verifying installation...\n'
sleep 3
bash "$REPO_ROOT/scripts/verify.sh"
