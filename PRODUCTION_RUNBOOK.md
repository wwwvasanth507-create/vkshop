# VKShop — Production Operations Runbook

This document provides explicit operational procedures and step-by-step commands for managing, maintaining, troubleshooting, and recovering the **VKShop** multi-server infrastructure.

---

## 🛠️ 1. Deployment & Rollback Procedures

### Standard Production Deployment (Render)
1. Push release tag or main branch to Git repository:
   ```bash
   git tag -a v1.2.0 -m "Production release v1.2.0"
   git push origin v1.2.0
   ```
2. Trigger deployment on primary Render instance `VKSHOP-API-1`.
3. Monitor zero-downtime startup via `/ready` endpoint:
   ```bash
   curl -i https://vkshop-api-1.onrender.com/ready
   ```
4. Verify HTTP 200 response with PostgreSQL, S3, and Redis connected.
5. Deploy remaining nodes (`VKSHOP-API-2`, `VKSHOP-API-3`) sequentially.

### Rollback Procedure
If a critical issue is detected:
1. Revert Render environment build to previous successful Git commit or image.
2. If database schema was migrated, run Alembic downgrade:
   ```bash
   flask db downgrade -1
   ```
3. Restart application workers:
   ```bash
   pkill -HUP gunicorn
   ```

---

## 🖥️ 2. Multi-Server Node Management

Access the **Infrastructure Management Dashboard** at `/admin/infrastructure` (Admin authorization required).

### Add a New Server Node
1. Provision a new Render web service or Docker container with standard environment variables.
2. Set `VKSHOP_SERVER_ID=srv-render-node-X`.
3. Node will automatically register on startup via `server_registry.heartbeat()`.

### Disable or Drain a Server Node
1. Open `/admin/infrastructure`.
2. Locate target node card (e.g., `VKSHOP-API-2`).
3. Click **Disable Node** or send POST request:
   ```bash
   curl -X POST https://vkshop-api-1.onrender.com/admin/infrastructure/toggle \
     -H "Content-Type: application/json" \
     -d '{"server_id": "VKSHOP-API-2", "enabled": false}'
   ```
4. Incoming traffic will bypass disabled node while active requests complete.

### Server Node Auto-Recovery
- Health monitor pings all registered nodes every 30 seconds.
- Nodes failing 3 consecutive health checks are automatically marked `UNHEALTHY`.
- When health check passes again, node transitions to `ONLINE` and resumes receiving traffic.

---

## 🔑 3. Secret & Credential Rotation

### Rotating S3 / R2 Access Keys
1. Generate new Access Key & Secret Key in S3/Cloudflare R2 Console.
2. Update `S3_ACCESS_KEY` and `S3_SECRET_KEY` on Render Environment Settings.
3. Perform rolling restart of Gunicorn workers.
4. Revoke old Access Key pair in cloud console.

### Rotating PostgreSQL Passwords
1. Update user password in PostgreSQL server:
   ```sql
   ALTER USER vkshop_user WITH PASSWORD 'new_secure_password';
   ```
2. Update `DATABASE_URL` across all server nodes.
3. Restart nodes.

---

## 🛢️ 4. Database Troubleshooting & Recovery

### Connection Pool Exhaustion / Leaks
**Symptom**: `QueuePool limit of size 10 overflow 20 reached, connection timed out`.

**Troubleshooting Steps**:
1. Check active database connections:
   ```sql
   SELECT count(*), state, client_addr FROM pg_stat_activity GROUP BY state, client_addr;
   ```
2. Identify queries exceeding timeout thresholds:
   ```sql
   SELECT pid, now() - query_start AS duration, query FROM pg_stat_activity WHERE state != 'idle' ORDER BY duration DESC;
   ```
3. Terminate stuck connections if necessary:
   ```sql
   SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE pid = <target_pid>;
   ```
4. Verify `pool_pre_ping=True` and `pool_recycle=300` are active in `database.py`.

### Database Backup & Restore
- **Backup**:
  ```bash
  pg_dump -U vkshop_user -h ep-db.render.com -d ecommerce -F c -b -v -f vkshop_backup_$(date +%F).dump
  ```
- **Restore**:
  ```bash
  pg_restore -U vkshop_user -h ep-db.render.com -d ecommerce -v -c vkshop_backup_2026-09-26.dump
  ```

---

## ☁️ 5. Storage Operations & Outage Recovery

### Storage AccessDenied / Permission Errors
- **Root Cause**: Bucket listing (`ListAllMyBuckets` / `ListBucket`) permission missing from IAM user / API token.
- **Resolution**: `StorageService` in `services/storage.py` handles this automatically by bypassing bucket-level checks and using direct object operations (`PutObject`/`GetObject`/`HeadObject`).

### Handling Object Storage Outages
If S3/R2 is temporarily unreachable:
1. Application logs warning and returns HTTP 503 for upload routes.
2. Read operations fallback gracefully to cached media or placeholder assets where appropriate.
3. Gunicorn workers do not crash due to bounded request timeouts (`connect_timeout=5s`).

---

## ⚡ 6. Redis Failure & Recovery

### Redis Unavailability
- When Redis fails, `services/redis_service.py` logs an error and automatically falls back to thread-safe in-memory caching (`threading.Lock()`).
- Sessions and critical business data remain fully preserved in PostgreSQL.
- When Redis connection is restored, cache fallback automatically resumes using Redis server.

---

## 🚨 7. Troubleshooting 502 Bad Gateway Errors

### Potential Root Causes & Solutions:
1. **Worker Thread Starvation**:
   - *Cause*: Long-running blocking HTTP calls or image processing blocking Gunicorn threads.
   - *Fix*: Ensure Gunicorn is configured with `gthread` worker class (`gunicorn.conf.py`) with `workers = 2`, `threads = 4`. Heavy background tasks (image optimization, invoice creation) are offloaded to `services/background_jobs.py`.
2. **Slow Database Connections**:
   - *Fix*: Keep `DATABASE_POOL_SIZE` at 10 and `DATABASE_MAX_OVERFLOW` at 20. Ensure indexes on `products(id)`, `orders(id, user_id)`, `users(id)`.
3. **Storage Connection Timeout**:
   - *Fix*: MinIO/S3 timeout set to 5s. Presigned upload URLs (`generate_presigned_upload_url`) offload heavy file uploads directly from client to S3 bucket.

---

## 🔒 8. High Load & Flash Sale Management

### Stock Deduction Under Concurrency
To prevent negative inventory or duplicate orders during peak events:
- Single-winner atomic SQL deduction:
  ```sql
  UPDATE products SET stock = stock - :qty WHERE id = :id AND stock >= :qty;
  ```
- Combined with Redis lock `lock:product:<id>` for strict sequence guarantees.
