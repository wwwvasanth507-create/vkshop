# VKShop — Local Ubuntu Server Production Deployment Guide

This guide provides step-by-step instructions for deploying **VKShop** on a **Local Ubuntu Server** (Ubuntu 22.04 LTS or 24.04 LTS) using **PostgreSQL** as the exclusive relational database, **Redis** for distributed sessions & caching, **Gunicorn** managed by **Systemd**, and **Nginx** as the high-performance reverse proxy and static media server.

---

## 🏗️ Architecture Overview (Local Ubuntu Server)

```
                            Client Browser / Mobile App
                                         │
                                         ▼
                            Nginx (Port 80 / 443 SSL)
                                         │
                 ┌───────────────────────┴───────────────────────┐
                 │                                               │
   Direct Static Asset Serving                      Reverse Proxy (`http://127.0.0.1:5000`)
   `/static/` & `/static/uploads/`                               │
                 │                                               ▼
                 │                               Gunicorn WSGI Application Server
                 │                               (Systemd Service: `vkshop.service`)
                 │                                               │
                 └───────────────────────┬───────────────────────┘
                                         │
                    ┌────────────────────┼────────────────────┐
                    │                    │                    │
           PostgreSQL 16 Database   Local Persistent Storage   Redis 7 Server
           (Exclusive Source of Truth) (`/static/uploads/`)    (Sessions, Cache & Locks)
```

---

## 🛠️ Step 1: System Dependencies Installation

Update system packages and install required server components:

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3 python3-pip python3-venv \
    postgresql postgresql-contrib \
    redis-server nginx \
    libpq-dev libjpeg-dev zlib1g-dev \
    git curl build-essential
```

---

## 🛢️ Step 2: PostgreSQL Database Configuration

1. Access PostgreSQL shell:
   ```bash
   sudo -u postgres psql
   ```

2. Create dedicated database user and database:
   ```sql
   CREATE USER vkshop_user WITH PASSWORD 'vkshop_secure_password';
   CREATE DATABASE ecommerce OWNER vkshop_user;
   GRANT ALL PRIVILEGES ON DATABASE ecommerce TO vkshop_user;
   \q
   ```

3. Enable PostgreSQL service:
   ```bash
   sudo systemctl enable --now postgresql
   ```

---

## ⚡ Step 3: Redis Server Setup

1. Start and enable Redis service:
   ```bash
   sudo systemctl enable --now redis-server
   ```

2. Test Redis connection:
   ```bash
   redis-cli ping
   # Expected output: PONG
   ```

---

## 📂 Step 4: Application Installation & Virtual Environment

1. Prepare project deployment directory:
   ```bash
   sudo mkdir -p /var/www/vkshop
   sudo chown -R $USER:$USER /var/www/vkshop
   cd /var/www/vkshop
   ```

2. Clone repository or copy project files into `/var/www/vkshop`.

3. Create Python virtual environment and install dependencies:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install --upgrade pip setuptools wheel
   pip install -r requirements.txt
   ```

4. Configure environment variables:
   ```bash
   cp .env.example .env
   nano .env
   ```
   Set `SECRET_KEY`, `DATABASE_URL=postgresql+psycopg://vkshop_user:vkshop_secure_password@127.0.0.1:5432/ecommerce`, and `REDIS_URL=redis://127.0.0.1:6379/0`.

---

## ⚙️ Step 5: Systemd Service Configuration (Gunicorn)

1. Copy service file to Systemd directory:
   ```bash
   sudo cp vkshop.service /etc/systemd/system/vkshop.service
   ```

2. Reload Systemd and start application service:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable --now vkshop
   ```

3. Check service status:
   ```bash
   sudo systemctl status vkshop
   ```

---

## 🌐 Step 6: Nginx Reverse Proxy Setup

1. Copy Nginx configuration file:
   ```bash
   sudo cp nginx.conf /etc/nginx/sites-available/vkshop
   ```

2. Enable site configuration and remove default page:
   ```bash
   sudo ln -sf /etc/nginx/sites-available/vkshop /etc/nginx/sites-enabled/
   sudo rm -f /etc/nginx/sites-enabled/default
   ```

3. Test configuration and reload Nginx:
   ```bash
   sudo nginx -t
   sudo systemctl reload nginx
   ```

---

## 🐳 Optional Step 7: Containerized Deployment via Docker Compose

If preferred, VKShop can be deployed via Docker Compose with a single command:

```bash
docker compose up -d --build
```

Services started:
- `vkshop_web`: Gunicorn Web Server (Port 5000)
- `vkshop_postgres`: PostgreSQL 16 (Port 5432)
- `vkshop_redis`: Redis 7 (Port 6379)

---

## 🏥 Step 8: Health & Verification Checks

1. **Liveness Check**:
   ```bash
   curl -i http://127.0.0.1:5000/live
   # Response: HTTP 200 OK {"status":"healthy"}
   ```

2. **Readiness Probe**:
   ```bash
   curl -i http://127.0.0.1:5000/ready
   # Response: HTTP 200 OK {"database":"connected","redis":"connected","status":"ok"}
   ```

3. **Database Migration Audit**: Database tables and adaptive schema migrations run automatically on startup via `init_db(app)`.
