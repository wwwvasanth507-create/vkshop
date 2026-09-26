# VKShop — Final Production Deployment Architecture & Guide

This document outlines the complete production deployment architecture, environment setup, database pooling, persistent object storage, multi-server registration, health monitoring, load balancing, and Android application configuration for **VKShop**.

---

## 🏗️ 1. High-Level Architecture Overview

```
                        Cloudflare CDN / Edge WAF
                                   │
                    ┌──────────────┴──────────────┐
                    │                             │
          VKShop Load Balancer / Reverse Proxy Router
                    │                             │
       ┌────────────┼─────────────────────────────┼────────────┐
       │            │                             │            │
VKShop Server 1  VKShop Server 2            VKShop Server 3  Flutter Android App
(Render Instance 1) (Render Instance 2)     (Render Instance 3) (Production REST API)
       │            │                             │            │
       └────────────┴──────────────┬──────────────┴────────────┘
                                   │
              ┌────────────────────┼────────────────────┐
              │                    │                    │
     Central PostgreSQL      Cloud Object Storage   Redis Session/Cache
     (Single Source of Truth)  (AWS S3 / R2 Bucket)   (Cluster Cache & Locks)
```

### Key Architectural Guarantee:
- **Stateless Backend Nodes**: All server instances share PostgreSQL, Redis, and Object Storage.
- **Zero Local Disk Dependency**: All product images, user avatars, seller documents, and invoices are stored exclusively in S3-compatible cloud object storage.

---

## 🔑 2. Complete Environment Variables Reference

Configure the following environment variables on Render / Server Instances:

| Variable | Required | Production Value / Example | Purpose |
|---|---|---|---|
| `FLASK_ENV` | Yes | `production` | Enables production security & logging mode |
| `FLASK_DEBUG` | Yes | `False` | Disables Flask debug mode |
| `SECRET_KEY` | Yes | `<64-hex-char-secure-secret>` | Signed cookies and session CSRF protection |
| `DATABASE_URL` | Yes | `postgresql://vkshop_user:pass@ep-db.render.com/ecommerce` | Central PostgreSQL connection URI |
| `DATABASE_POOL_SIZE` | No | `10` | SQLAlchemy connection pool size |
| `DATABASE_MAX_OVERFLOW` | No | `20` | Maximum pool overflow connections |
| `S3_ENDPOINT` | Yes | `https://<account-id>.r2.cloudflarestorage.com` | Object Storage API endpoint URL |
| `S3_ACCESS_KEY` | Yes | `<access-key-id>` | Storage Access Key ID |
| `S3_SECRET_KEY` | Yes | `<secret-access-key>` | Storage Secret Access Key |
| `S3_BUCKET` | Yes | `vkshop-media-production` | Target Object Storage Bucket |
| `S3_REGION` | No | `us-east-1` | S3 Region |
| `STORAGE_PUBLIC_URL` | Yes | `https://pub-media.vkshop.com` | CDN Base URL for public media delivery |
| `ALLOW_LOCAL_STORAGE_FALLBACK` | Yes | `False` | Disables fallback to temporary disk in production |
| `REDIS_URL` | Yes | `redis://default:pass@redis-10000.c1.cloud.redislabs.com:10000` | Distributed Session & Rate-Limiter Redis URI |
| `WEB_CONCURRENCY` | No | `2` | Gunicorn Worker Count |
| `GUNICORN_THREADS` | No | `4` | Gunicorn Threads per Worker |
| `GUNICORN_TIMEOUT` | No | `60` | Gunicorn Worker Timeout in Seconds |
| `VKSHOP_SERVER_ID` | Yes | `srv-render-primary-1` | Unique ID for server node registration |

---

## 🛢️ 3. Central Database Setup (PostgreSQL)

1. **Connection Pooling**: SQLAlchemy pool pre-ping (`pool_pre_ping=True`) is active to automatically drop stale connections.
2. **Schema Migration**: Database migrations run automatically on startup via `init_db(app)` in `database.py`. Missing columns or tables are created adaptively without dropping data.
3. **Atomic Stock Updates**: Stock deduction uses SQL atomic statement:
   `UPDATE products SET stock = stock - 1 WHERE id = :id AND stock >= 1`
   guaranteeing single-winner concurrency during flash sales.

---

## ☁️ 4. Storage Architecture (S3 / Cloudflare R2)

### Bucket Directory Layout:
```
bucket/
  ├── products/
  ├── product-thumbnails/
  ├── banners/
  ├── users/
  ├── categories/
  ├── documents/
  ├── invoices/
  └── temporary/
```

- **S3 AccessDenied Resilience**: `StorageService` in `services/storage.py` decouples client initialization from bucket creation checks. If the S3 credentials lack `ListBucket` / `ListAllMyBuckets` permissions, `ensure_bucket()` catches the exception gracefully and allows `PutObject`, `GetObject`, `DeleteObject`, and `HeadObject` calls to execute cleanly.

---

## ⚡ 5. Redis Setup & Graceful Fallbacks

- `services/redis_service.py` handles Redis caching, rate limiting, and distributed locks.
- If Redis is temporarily unreachable, `RedisService` falls back to thread-safe in-memory caching and mutex locking without crashing HTTP workers.

---

## 🚀 6. Gunicorn & Render Deployment

Render `render.yaml` startup command:
```bash
gunicorn -c gunicorn.conf.py app:app
```
`gunicorn.conf.py` binds to `0.0.0.0:$PORT` using `gthread` worker class with configurable workers, threads, and timeout options.

---

## 🏥 7. Health & Readiness Probes

- `/health` & `/live`: Returns `{"status": "healthy"}` instantly (HTTP 200) without I/O calls.
- `/ready`: Diagnostic readiness probe testing PostgreSQL, S3, and Redis connectivity.

---

## 📱 8. Android App Build Procedure

Navigate to `android_app/`:
```bash
cd android_app
flutter pub get
flutter analyze
flutter build apk --release
```
The output APK is stored in `android_app/build/app/outputs/flutter-apk/app-release.apk`.

---

## 🔄 9. Zero Downtime Deployment & Rollback Procedure

1. Deploy new backend code to Render instance `VKSHOP-API-2`.
2. Wait for `/ready` endpoint to return HTTP 200.
3. Enable instance in Server Registry `/admin/infrastructure`.
4. Drain and update `VKSHOP-API-1`.
