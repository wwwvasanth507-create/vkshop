#!/usr/bin/env bash
# ==============================================================================
# VKShop — Automated Local Ubuntu Server Setup & Deployment Script
# Target OS: Ubuntu 22.04 / 24.04 LTS
# Includes: Git Clone, PostgreSQL 16, Redis 7, Nginx, Gunicorn Systemd, Cloudflare Tunnel
# ==============================================================================

set -e

REPO_URL="https://github.com/wwwvasanth507-create/vkshop.git"
APP_DIR="/var/www/vkshop"
DB_NAME="ecommerce"
DB_USER="vkshop_user"
DB_PASS="vkshop_secure_password"

echo "========================================================================"
echo "🚀 Starting VKShop Automated Installation on Local Ubuntu Server"
echo "========================================================================"

# 1. Update system packages and install core dependencies
echo "[STEP 1/7] Updating system packages and installing dependencies..."
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3 python3-pip python3-venv \
    postgresql postgresql-contrib \
    redis-server nginx \
    libpq-dev libjpeg-dev zlib1g-dev \
    git curl build-essential wget

# 2. Setup or Git Pull Application Repository
echo "[STEP 2/7] Setting up application directory and pulling code from Git..."
if [ -d "$APP_DIR/.git" ]; then
    echo "Existing repository found at $APP_DIR. Pulling latest code..."
    cd "$APP_DIR"
    git pull origin main || git pull origin master
else
    echo "Cloning repository from $REPO_URL to $APP_DIR..."
    sudo mkdir -p "$APP_DIR"
    sudo chown -R $USER:$USER "$APP_DIR"
    git clone "$REPO_URL" "$APP_DIR"
    cd "$APP_DIR"
fi

# 3. Setup PostgreSQL Database & User
echo "[STEP 3/7] Setting up PostgreSQL Database and User..."
sudo systemctl enable --now postgresql
sudo -u postgres psql -c "CREATE USER $DB_USER WITH PASSWORD '$DB_PASS';" || echo "User $DB_USER already exists."
sudo -u postgres psql -c "CREATE DATABASE $DB_NAME OWNER $DB_USER;" || echo "Database $DB_NAME already exists."
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE $DB_NAME TO $DB_USER;" || true

# 4. Setup Redis Server
echo "[STEP 4/7] Setting up Redis Server..."
sudo systemctl enable --now redis-server

# 5. Setup Python Virtual Environment and Install Requirements
echo "[STEP 5/7] Setting up Python Virtual Environment..."
if [ ! -d "$APP_DIR/venv" ]; then
    python3 -m venv "$APP_DIR/venv"
fi

source "$APP_DIR/venv/bin/activate"
pip install --upgrade pip setuptools wheel
pip install -r "$APP_DIR/requirements.txt"

# Create .env file if missing
if [ ! -f "$APP_DIR/.env" ]; then
    echo "Creating production .env file..."
    cp "$APP_DIR/.env.example" "$APP_DIR/.env"
    # Generate random secret key
    SECRET_HEX=$(python3 -c "import secrets; print(secrets.token_hex(32))")
    sed -i "s/SECRET_KEY=.*/SECRET_KEY=$SECRET_HEX/" "$APP_DIR/.env"
    sed -i "s|DATABASE_URL=.*|DATABASE_URL=postgresql+psycopg://$DB_USER:$DB_PASS@127.0.0.1:5432/$DB_NAME|" "$APP_DIR/.env"
fi

# Initialize database schema & seed initial admin data
echo "Seeding database..."
python3 "$APP_DIR/seed.py" || echo "Seeder executed with warnings."

# Ensure directory structure and ownership permissions for www-data
mkdir -p "$APP_DIR/logs" "$APP_DIR/static/uploads"
sudo chown -R www-data:www-data "$APP_DIR"
sudo chmod -R 775 "$APP_DIR/logs" "$APP_DIR/static/uploads"

# 6. Enable Gunicorn Systemd Service & Nginx Reverse Proxy
echo "[STEP 6/7] Enabling Systemd Service & Nginx Reverse Proxy..."
sudo cp "$APP_DIR/vkshop.service" /etc/systemd/system/vkshop.service
sudo systemctl daemon-reload
sudo systemctl enable --now vkshop

sudo cp "$APP_DIR/nginx.conf" /etc/nginx/sites-available/vkshop
sudo ln -sf /etc/nginx/sites-available/vkshop /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl reload nginx

# 7. Install & Configure Cloudflare Tunnel (cloudflared)
echo "[STEP 7/7] Installing Cloudflare Tunnel (cloudflared)..."
if ! command -v cloudflared &> /dev/null; then
    wget -q https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb
    sudo dpkg -i cloudflared-linux-amd64.deb
    rm -f cloudflared-linux-amd64.deb
fi

echo "========================================================================"
echo "✅ VKShop Local Ubuntu Server Installation Complete!"
echo "========================================================================"
echo "Status Checks:"
echo "  - Gunicorn Service: sudo systemctl status vkshop"
echo "  - Nginx Proxy:       sudo systemctl status nginx"
echo "  - PostgreSQL:        sudo systemctl status postgresql"
echo "  - Redis:             sudo systemctl status redis-server"
echo ""
echo "To connect Cloudflare Tunnel for public HTTPS access, run:"
echo "  sudo cloudflared service install <YOUR_CLOUDFLARE_TUNNEL_TOKEN>"
echo "  sudo systemctl enable --now cloudflared"
echo "========================================================================"
