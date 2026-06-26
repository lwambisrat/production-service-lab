#!/usr/bin/env bash
# setup-firewall.sh — configure UFW for the production service lab.
#
# Protection philosophy (two layers):
#   PRIMARY:   Services bind to 127.0.0.1 — kernel rejects external connections.
#   SECONDARY: UFW blocks ports 3001-3003 — enforced even if a service
#              is misconfigured to bind on 0.0.0.0.
#
# Run with: sudo bash scripts/setup-firewall.sh

set -euo pipefail

echo "==> Configuring UFW firewall..."

# Install ufw if missing
if ! command -v ufw &>/dev/null; then
    apt-get install -y ufw
fi

# Allow SSH first — prevents locking yourself out
ufw allow OpenSSH

# Allow Nginx — the only public-facing port
ufw allow 80/tcp comment 'Nginx public entrypoint (ride-booking)'

# Block direct access to internal services
ufw deny 3001/tcp comment 'ride-booking - internal only'
ufw deny 3002/tcp comment 'driver-matching - internal only'
ufw deny 3003/tcp comment 'ride-dispatch - internal only'

# Default policy
ufw default deny incoming
ufw default allow outgoing

# Enable
ufw --force enable

echo ""
echo "==> Firewall status:"
ufw status verbose
