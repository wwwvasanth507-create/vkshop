# Deploying VKShop on Render with PostgreSQL & Persistent Cloud Storage

This document provides step-by-step instructions for deploying **VKShop** on [Render](https://render.com) using PostgreSQL and S3-compatible persistent object storage (such as Cloudflare R2, AWS S3, MinIO, or Supabase Storage).

---

## ⚠️ Important Storage Tier & Quota Disclaimer

> [!WARNING]
> No cloud provider offers unlimited free storage. Free tiers (e.g. Render PostgreSQL free plan, Cloudflare R2 free quota, AWS S3 Free Tier) come with explicit storage limits, monthly bandwidth caps, request rate limits, and inactivity policies.
> - **Render Free PostgreSQL**: Databases on Render's free tier expire after 90 days if not upgraded, and disk size is limited to 1 GB. For production, use a paid PostgreSQL instance or managed provider (Supabase, Neon, AWS RDS).
> - **Object Storage**: Free tiers (e.g. Cloudflare R2 10 GB/month free, AWS S3 5 GB free for 12 months) incur costs once usage exceeds the quota. VKShop optimizes uploaded images (WebP compression, max 1600px width/height) to preserve bandwidth and storage efficiency without enforcing artificial user/product caps in code.

---

## 1. Prerequisites

Before starting deployment, ensure you have:
1. A GitHub account containing the [VKShop repository](https://github.com/wwwvasanth507-create/vkshop).
2. A [Render account](https://dashboard.render.com).
3. An S3-compatible object storage bucket (Cloudflare R2, AWS S3, Supabase S3, or self-hosted MinIO).

---

## 2. PostgreSQL Setup on Render

1. Log into [Render Dashboard](https://dashboard.render.com).
2. Click **New +** -> **PostgreSQL**.
3. Configure the database:
   - **Name**: `vkshop-db`
   - **Database**: `ecommerce`
   - **User**: `vkshop_user`
   - **Region**: Choose the region closest to your target audience.
   - **Plan**: Select **Free** (or Starter/Standard for production use).
4. Click **Create Database**.
5. Once created, copy the **Internal Database URL** (or External Connection String).
   *Note: Render connection strings starting with `postgres://` are automatically normalized by VKShop to `postgresql://`.*

---

## 3. Cloudflare R2 / S3 Object Storage Bucket Setup

1. **Create R2 Bucket**:
   - Log into [Cloudflare Dashboard](https://dash.cloudflare.com) -> **R2**.
   - Click **Create bucket** -> Name: `vkshop-uploads`.
   - Choose location preference (e.g. Automatic or closest region).

2. **Generate API Token Credentials**:
   - Navigate to **R2 Overview** -> **Manage R2 API Tokens**.
   - Click **Create API Token**.
   - Set Permissions to **Edit** (Object Read and Write).
   - Under Scope, select `vkshop-uploads` or All Buckets.
   - Record the generated credentials:
     - **Access Key ID** -> `MINIO_ACCESS_KEY`
     - **Secret Access Key** -> `MINIO_SECRET_KEY`
     - **S3 API Endpoint** -> `MINIO_ENDPOINT` (e.g. `<ACCOUNT_ID>.r2.cloudflarestorage.com`)

3. **Configure Public Asset Delivery**:
   - In R2 Bucket Settings, enable **Public Development URL** or connect a **Custom Domain** (e.g. `https://pub-xxxx.r2.dev` or `https://cdn.yourdomain.com`).
   - Copy this base URL -> `STORAGE_PUBLIC_URL`.

> [!IMPORTANT]
> **Public Asset vs Private Document Security Warning**:
> - Public product, store, banner, and category images are served directly via `STORAGE_PUBLIC_URL`.
> - Sensitive verification documents (Aadhaar front/back, seller photo, signature, payment screenshots, complaint proofs) are stored under the `private/` key prefix.
> - `resolve_image_url()` automatically intercepts `private/` paths and routes them through VKShop's authenticated Flask endpoint (`/private/file/<path>`), ensuring unauthenticated access and direct public CDN exposure are strictly blocked.

---

## 4. Render Web Service Deployment

1. On Render Dashboard, click **New +** -> **Web Service**.
2. Connect your GitHub repository `vkshop`.
3. Configure the Web Service:
   - **Name**: `vkshop`
   - **Region**: Same region as your database.
   - **Branch**: `main`
   - **Runtime**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn -c gunicorn.conf.py app:app`
   - **Health Check Path**: `/health`

---

## 5. Environment Variables Configuration

In the Render Web Service **Environment** tab, add the following variables:

| Key | Value / Source | Description |
|---|---|---|
| `FLASK_ENV` | `production` | Enables production mode & security flags |
| `FLASK_DEBUG` | `False` | Disables debug mode |
| `SECRET_KEY` | *(Click "Generate")* | Secret key for Flask sessions & CSRF |
| `DATABASE_URL` | *(Link from `vkshop-db`)* | PostgreSQL connection string |
| `STORAGE_PROVIDER` | `s3` | S3-compatible cloud storage driver |
| `STORAGE_PUBLIC_URL` | `https://your-public-bucket.r2.dev` | Public URL prefix for assets |
| `MINIO_ENDPOINT` | `your-s3-endpoint.com` | S3 API endpoint hostname |
| `MINIO_ACCESS_KEY` | `your-access-key` | S3 Access Key ID |
| `MINIO_SECRET_KEY` | `your-secret-key` | S3 Secret Access Key |
| `MINIO_BUCKET_NAME` | `vkshop-uploads` | Target bucket name |
| `MINIO_SECURE` | `True` | Set `True` for HTTPS (port 443) |
| `ALLOW_LOCAL_STORAGE_FALLBACK` | `False` | Disables writing persistent uploads to Render disk |
| `IMAGE_MAX_WIDTH` | `1600` | Max image width optimization threshold |
| `IMAGE_MAX_HEIGHT` | `1600` | Max image height optimization threshold |
| `IMAGE_WEBP_QUALITY` | `82` | WebP compression quality (0-100) |
| `IMAGE_MAX_UPLOAD_MB` | `15` | Max allowed upload size per file |
| `SESSION_COOKIE_SECURE` | `True` | Enforces HTTPS-only cookies |

---

## 6. First Deployment & Automatic Database Initialization

1. Click **Deploy Web Service**.
2. Render will run `pip install -r requirements.txt` and start Gunicorn.
3. On first startup:
   - VKShop connects to PostgreSQL.
   - `init_db()` runs `run_adaptive_migrations()`, automatically creating tables (`users`, `products`, `orders`, `store_profiles`, etc.) and database indexes.
   - If the database is empty, seed data is inserted automatically.

---

## 7. Post-Deployment Verification Steps

### A. Health Check Test
Visit `https://<your-render-app>.onrender.com/health` in your browser.
Expected Response:
```json
{"status": "ok"}
```

### B. Product Image Upload Test
1. Log in as a seller or admin.
2. Add a new product with a primary image and gallery images.
3. Inspect the product image URL:
   - It should point to `STORAGE_PUBLIC_URL/products/<uuid>.webp`.
   - The image is optimized in WebP format.

### C. Private Verification Document Security Test
1. Register a new seller with Aadhaar front/back and signature documents.
2. Inspect the document links:
   - Paths will be in format `private/seller-documents/<user-id>/<uuid>.webp`.
   - Attempting to view a private document anonymously or as an unauthorized customer returns `401 Unauthorized` or `404 Not Found`.
   - Authorized admins can inspect documents via `/private/file/<filename>`.

### D. Restart & Redeployment Persistence Test
1. Manual Trigger: In Render Dashboard, click **Manual Deploy** -> **Clear Build Cache & Deploy**.
2. After deployment completes:
   - Products, users, and orders remain intact in PostgreSQL.
   - Images remain accessible from cloud object storage.
   - No images are lost due to Render filesystem resets.

---

## 8. Troubleshooting

| Issue | Root Cause | Solution |
|---|---|---|
| `RuntimeError: Production mode requires PostgreSQL` | `DATABASE_URL` is missing | Attach PostgreSQL database or set `DATABASE_URL` in environment. |
| `RuntimeError: Persistent object storage is unavailable` | S3 credentials invalid or `ALLOW_LOCAL_STORAGE_FALLBACK=False` active | Verify `MINIO_ENDPOINT`, `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY`, `MINIO_BUCKET_NAME`. |
| Gunicorn timeout on file upload | File size too large | Image optimization handles up to 15MB. Ensure client connection speed is stable. |
| Mixed content (HTTP images on HTTPS site) | `STORAGE_PUBLIC_URL` uses `http://` | Update `STORAGE_PUBLIC_URL` to use `https://`. |
