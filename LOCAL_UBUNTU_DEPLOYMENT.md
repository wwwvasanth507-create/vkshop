# VKShop — Local Ubuntu Server Complete Setup & Deployment Guide

This guide provides inch-by-inch, step-by-step terminal commands for deploying **VKShop** from the GitHub repository (`https://github.com/wwwvasanth507-create/vkshop.git`) onto a **Local Ubuntu Server** (Ubuntu 22.04 LTS or 24.04 LTS).

The setup includes:
- **Git Repository Pull / Clone**
- **PostgreSQL 16** (Exclusive Relational Database Engine)
- **Redis 7** (Distributed Session & Rate-Limiting Engine)
- **Gunicorn WSGI Server** (Managed by Systemd service `vkshop.service`)
- **Nginx** (High-Performance Reverse Proxy & Media Server)
- **Cloudflare Tunnel** (Auto-restarting Systemd service `cloudflared.service` for public HTTPS access without open router ports)

---

## ⚡ Quick One-Command Automated Setup

You can run the automated setup script included in the repository:

```bash
cd /var/www/vkshop
bash setup_ubuntu_server.sh
```

---

## 🛠️ Inch-by-Inch Step-by-Step Installation Guide

### Step 1: Install Package Dependencies

Update apt repositories and install all required system packages:

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3 python3-pip python3-venv \
    postgresql postgresql-contrib \
    redis-server nginx \
    libpq-dev libjpeg-dev zlib1g-dev \
    git curl build-essential wget
```

---

### Step 2: Clone or Pull Repository Code

Clone repository from GitHub to `/var/www/vkshop`:

```bash
# Create directory and set permissions
sudo mkdir -p /var/www/vkshop
sudo chown -R $USER:$USER /var/www/vkshop

# Clone repository from GitHub
git clone https://github.com/wwwvasanth507-create/vkshop.git /var/www/vkshop

# Navigate to project directory
cd /var/www/vkshop

# (Optional) If repository is already cloned, pull latest code:
git pull origin main
```

---

### Step 3: Setup PostgreSQL Database & User

Start PostgreSQL service and create database + user:

```bash
# Enable & start PostgreSQL service
sudo systemctl enable --now postgresql

# Create database user with password
sudo -u postgres psql -c "CREATE USER vkshop_user WITH PASSWORD 'vkshop_secure_password';"

# Create database owned by user
sudo -u postgres psql -c "CREATE DATABASE ecommerce OWNER vkshop_user;"

# Grant privileges
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE ecommerce TO vkshop_user;"
```

---

### Step 4: Setup Redis Server

Enable and verify Redis service:

```bash
# Enable & start Redis server
sudo systemctl enable --now redis-server

# Verify Redis connection
redis-cli ping
# Expected output: PONG
```

---

### Step 5: Setup Python Virtual Environment & Configuration

Create Python virtual environment, install requirements, and configure environment variables:

```bash
cd /var/www/vkshop

# Create Python virtual environment
python3 -m venv venv

# Activate virtual environment
source venv/bin/activate

# Upgrade pip and install application dependencies
pip install --upgrade pip setuptools wheel
pip install -r requirements.txt

# Create .env file from template
cp .env.example .env
```

---

### Step 6: Enable Gunicorn Systemd Service & Nginx

Install Systemd unit file and Nginx reverse proxy configuration:

```bash
# Install Systemd service for Gunicorn
sudo cp vkshop.service /etc/systemd/system/vkshop.service
sudo systemctl daemon-reload
sudo systemctl enable --now vkshop

# Verify Gunicorn service status
sudo systemctl status vkshop

# Configure Nginx reverse proxy
sudo cp nginx.conf /etc/nginx/sites-available/vkshop
sudo ln -sf /etc/nginx/sites-available/vkshop /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl reload nginx
```

---

### Step 7: Create & Connect Cloudflare Tunnel (Auto-Service)

Install Cloudflare Tunnel (`cloudflared`) and register it as an auto-restarting Systemd background service:

```bash
# 1. Download & Install cloudflared package
wget -q https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb
sudo dpkg -i cloudflared-linux-amd64.deb
rm -f cloudflared-linux-amd64.deb

# 2. Install Cloudflare Tunnel service using your token from Cloudflare Dashboard
# Replace <YOUR_CLOUDFLARE_TUNNEL_TOKEN> with your actual tunnel token:
sudo cloudflared service install <YOUR_CLOUDFLARE_TUNNEL_TOKEN>

# 3. Enable and start cloudflared service
sudo systemctl enable --now cloudflared

# 4. Check tunnel status
sudo systemctl status cloudflared
```

---

## 🏥 Step 8: Verification & Health Checks

Test health probe endpoints:

```bash
# Check Liveness probe
curl -i http://127.0.0.1:5000/live

# Check Readiness diagnostic probe
curl -i http://127.0.0.1:5000/ready
```
Expected output: `HTTP 200 OK {"database":"connected","redis":"connected","status":"ok"}`.
