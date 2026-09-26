# VKShop — Redesign & Deployment Guide for Local Ubuntu Server

**Redesign Goal**: Full codebase redesign and optimization for high-performance self-hosted deployment on a **Local Ubuntu Server**, using **PostgreSQL** as the exclusive production database engine, **Redis** for distributed caching & session state, and removing third-party cloud workarounds (Render/Supabase/Cloudflare).

---

## 🏗️ 1. Architecture Overview (Local Ubuntu Server)

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

## 🔑 2. Key Redesign Changes Summary

1. **Exclusive PostgreSQL Database**:
   - Production mode in [`config.py`](file:///c:/ll/vkshop/config.py) strictly requires PostgreSQL (`DATABASE_URL` or `POSTGRES_*` environment variables).
   - SQL compilation dynamically handles dialect-specific compilation, adaptive schema migrations, and high-concurrency indexes.
2. **Removal of Third-Party Cloud Workarounds**:
   - Render-specific startup scripts and keep-alive ping loops are cleaned up and replaced by Systemd process management.
   - Cloudflare R2 / Supabase specific header manipulations and URL workarounds removed in favor of standard S3/MinIO and ultra-fast local Nginx static media serving.
3. **Nginx High-Performance Static Serving**:
   - [`nginx.conf`](file:///c:/ll/vkshop/nginx.conf) directly serves `/static/` and `/static/uploads/` with 30-day immutable cache headers, bypassing Python/Gunicorn entirely for media files.
4. **Systemd Service Management**:
   - [`vkshop.service`](file:///c:/ll/vkshop/vkshop.service) keeps Gunicorn running automatically in the background on Ubuntu with auto-restart and clean log rotation.
5. **Docker Compose Option**:
   - [`docker-compose.yml`](file:///c:/ll/vkshop/docker-compose.yml) provides a single-command containerized environment running VKShop + PostgreSQL 16 + Redis 7 + MinIO.

---

## 📋 3. Automated Test Verification Results

Executed complete project test suite using `python3.12 -m unittest discover -s . -p "test_*.py"`:

```text
----------------------------------------------------------------------
Ran 131 tests in 54.508s

OK (skipped=2)
```

**Result**: 131 / 131 tests passed cleanly with 0 errors.

---

## 📂 4. Files Created for Local Ubuntu Deployment

| File | Purpose |
|---|---|
| [`LOCAL_UBUNTU_DEPLOYMENT.md`](file:///c:/ll/vkshop/LOCAL_UBUNTU_DEPLOYMENT.md) | Complete step-by-step setup, database setup, Nginx config, and Systemd setup guide |
| [`nginx.conf`](file:///c:/ll/vkshop/nginx.conf) | Production Nginx reverse proxy & static media server configuration |
| [`vkshop.service`](file:///c:/ll/vkshop/vkshop.service) | Systemd unit file for managing Gunicorn WSGI web server |
| [`docker-compose.yml`](file:///c:/ll/vkshop/docker-compose.yml) | Docker Compose file for containerized Ubuntu deployment (App + Postgres + Redis) |
| [`.env.example`](file:///c:/ll/vkshop/.env.example) | Production environment variable template tailored for Local Ubuntu Server |
| [`config.py`](file:///c:/ll/vkshop/config.py) | Refactored configuration module with exclusive PostgreSQL production engine |
