#!/bin/bash

set -e

echo "Updating packages..."
sudo apt update

echo "Installing dependencies..."
sudo apt install -y python3 python3-pip python3-venv nginx curl

echo "Creating virtual environment..."
python3 -m venv venv

echo "Activating virtual environment..."
source venv/bin/activate

echo "Installing Python dependencies..."
pip install -r requirements.txt

echo "Configuring service discovery..."
sudo bash -c 'cat >> /etc/hosts << EOF
127.0.0.1 service-a.internal
127.0.0.1 service-b.internal
127.0.0.1 service-c.internal
EOF'

echo "Installing systemd services..."
sudo cp systemd/*.service /etc/systemd/system/

echo "Reloading systemd..."
sudo systemctl daemon-reload

echo "Enabling services..."
sudo systemctl enable service-c service-b service-a

echo "Starting services..."
sudo systemctl start service-c
sudo systemctl start service-b
sudo systemctl start service-a

echo "Configuring nginx..."
sudo cp nginx/production-service-lab.conf /etc/nginx/sites-available/

if [ ! -L /etc/nginx/sites-enabled/production-service-lab ]; then
sudo ln -s /etc/nginx/sites-available/production-service-lab /etc/nginx/sites-enabled/
fi

sudo nginx -t
sudo systemctl restart nginx

echo "Installation complete."
