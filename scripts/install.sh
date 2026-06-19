#!/bin/bash

set -e

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CURRENT_USER="$(whoami)"

echo "Updating packages..."
sudo apt update

echo "Installing dependencies..."
sudo apt install -y python3 python3-pip python3-venv nginx curl

echo "Creating virtual environment..."
python3 -m venv "$REPO_DIR/venv"

echo "Installing Python dependencies..."
"$REPO_DIR/venv/bin/pip" install -r "$REPO_DIR/requirements.txt"

echo "Configuring service discovery..."
for host in service-a.internal service-b.internal service-c.internal; do
    if ! grep -q "$host" /etc/hosts; then
        echo "127.0.0.1 $host" | sudo tee -a /etc/hosts > /dev/null
    fi
done

echo "Installing systemd services..."
for service_file in "$REPO_DIR"/systemd/*.service; do
    dest="/etc/systemd/system/$(basename "$service_file")"
    sudo cp "$service_file" "$dest"
    sudo sed -i "s|User=lwambisrat|User=$CURRENT_USER|g" "$dest"
    sudo sed -i "s|/home/lwambisrat.guest/production-service-lab|$REPO_DIR|g" "$dest"
done

echo "Reloading systemd..."
sudo systemctl daemon-reload

echo "Enabling services..."
sudo systemctl enable service-c service-b service-a

echo "Starting services..."
sudo systemctl start service-c
sudo systemctl start service-b
sudo systemctl start service-a

echo "Configuring nginx..."
sudo cp "$REPO_DIR/nginx/production-service-lab.conf" /etc/nginx/sites-available/production-service-lab

if [ ! -L /etc/nginx/sites-enabled/production-service-lab ]; then
    sudo ln -s /etc/nginx/sites-available/production-service-lab /etc/nginx/sites-enabled/production-service-lab
fi

if [ -L /etc/nginx/sites-enabled/default ]; then
    sudo rm /etc/nginx/sites-enabled/default
fi

sudo nginx -t
sudo systemctl restart nginx

echo "Installation complete."
echo "Test with: curl http://localhost/service-a/health"
