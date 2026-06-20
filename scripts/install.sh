#!/usr/bin/env bash
# install.sh — idempotent deployment script for the production service lab.
# Safe to re-run. Uses sudo internally; do NOT run as: sudo bash install.sh
#
# Usage: bash scripts/install.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
DEPLOY_USER="${SUDO_USER:-$(logname 2>/dev/null || whoami)}"

step(){ printf '\n\033[1;34m==>\033[0m %s\n' "$1"; }

step "Production Service Lab Installer"
echo "    Project : $REPO_ROOT"
echo "    User    : $DEPLOY_USER"

# ---------------------------------------------------------------------------
step "1/7  System packages"
# ---------------------------------------------------------------------------
sudo apt-get update -qq
sudo apt-get install -y python3 python3-pip python3-venv nginx curl ufw rsync

# ---------------------------------------------------------------------------
step "2/7  Service discovery (/etc/hosts)"
# ---------------------------------------------------------------------------
for entry in \
    "127.0.0.1   service-a.internal" \
    "127.0.0.1   service-b.internal" \
    "127.0.0.1   service-c.internal"
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
step "3/7  Python virtual environment"
# ---------------------------------------------------------------------------
sudo -u "$DEPLOY_USER" python3 -m venv "$REPO_ROOT/venv"
sudo -u "$DEPLOY_USER" "$REPO_ROOT/venv/bin/pip" install -q -r "$REPO_ROOT/requirements.txt"
echo "    Done."

# ---------------------------------------------------------------------------
step "4/7  Systemd service files"
# ---------------------------------------------------------------------------
for svc in ride-dispatch driver-matching ride-booking; do
    sudo sed \
        -e "s|YOUR_USERNAME|$DEPLOY_USER|g" \
        -e "s|YOUR_PROJECT_PATH|$REPO_ROOT|g" \
        "$REPO_ROOT/systemd/${svc}.service" \
        | sudo tee "/etc/systemd/system/${svc}.service" > /dev/null
    echo "    Installed: /etc/systemd/system/${svc}.service"
done

sudo chmod +x "$REPO_ROOT/scripts/wait-for-deps.sh"
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
