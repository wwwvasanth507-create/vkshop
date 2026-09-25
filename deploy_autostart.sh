#!/bin/bash
set -e

echo "=================================================="
echo "  Deploying E-Commerce Server with Autostart"
echo "=================================================="

PROJECT_DIR="/home/vasanth-v/Desktop/E-COM"
cd "$PROJECT_DIR"

echo "[1/5] Stopping and removing any old service running on port 5000..."
sudo systemctl stop campusplayer 2>/dev/null || true
sudo systemctl disable campusplayer 2>/dev/null || true
sudo fuser -k 5000/tcp 2>/dev/null || true

echo "[2/5] Setting up Python Virtual Environment & installing requirements..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi

source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

echo "[3/5] Creating systemd autostart service for E-COM (ecom.service)..."
sudo tee /etc/systemd/system/ecom.service > /dev/null <<'EOF'
[Unit]
Description=E-Commerce Production Server (E-COM)
After=network.target redis-server.service
Wants=redis-server.service

[Service]
Type=simple
User=vasanth-v
WorkingDirectory=/home/vasanth-v/Desktop/E-COM
Environment="PATH=/home/vasanth-v/Desktop/E-COM/venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
ExecStart=/home/vasanth-v/Desktop/E-COM/venv/bin/python run_production.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

echo "[4/5] Reloading systemd, enabling and starting ecom.service..."
sudo systemctl daemon-reload
sudo systemctl enable ecom.service
sudo systemctl restart ecom.service

echo "[5/5] Checking Cloudflare Tunnel and autostart services..."
sudo systemctl enable cloudflared 2>/dev/null || true
sudo systemctl restart cloudflared 2>/dev/null || true

echo "=================================================="
echo "  SUCCESS! E-Commerce Server is Live & Autostarting!"
echo "=================================================="
sudo systemctl status ecom.service --no-pager
