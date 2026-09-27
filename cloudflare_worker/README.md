# Cloudflare Worker API Gateway for VKShop

Permanent Public Gateway: `https://home.vkshop.workers.dev`

## Overview
This Cloudflare Worker acts as the permanent public web and API gateway for VKShop. It proxies all incoming requests targeting `https://home.vkshop.workers.dev` to whichever active VPS or origin server (`ORIGIN_URL`) is currently serving the backend.

When your VPS domain, IP address, or hosting provider changes in the future, you **only** update the `ORIGIN_URL` environment variable in Cloudflare. The permanent gateway URL (`https://home.vkshop.workers.dev`) and mobile Flutter app will remain unchanged!

---

## Deployment Steps

### Option 1: Via Wrangler CLI (Recommended)

1. **Install Wrangler CLI**:
   ```bash
   npm install -g wrangler
   ```

2. **Authenticate with Cloudflare**:
   ```bash
   wrangler login
   ```

3. **Set Active VPS Origin URL**:
   In `wrangler.toml` or via secret command:
   ```bash
   wrangler secret put ORIGIN_URL
   # Enter your active VPS origin URL (e.g., https://your-current-vps-domain.com)
   ```

4. **Deploy to Cloudflare Workers**:
   ```bash
   cd cloudflare_worker
   wrangler deploy
   ```

---

### Option 2: Via Cloudflare Dashboard (GUI)

1. Log in to [Cloudflare Dashboard](https://dash.cloudflare.com/).
2. Navigate to **Workers & Pages** -> Click **Create Application** -> **Create Worker**.
3. Name the Worker: `home`.
4. Click **Deploy**, then **Edit Code**.
5. Copy & paste the contents of `worker.js` into the online editor and click **Save and Deploy**.
6. Go to **Settings** -> **Variables** -> Add Environment Variable:
   - Variable name: `ORIGIN_URL`
   - Value: `https://your-current-vps-domain.com` (Your current VPS origin address).
7. Click **Save and Deploy**.

---

## Testing Gateway Proxy

Test that the worker forwards requests to your origin:

```bash
# Gateway config check
curl -i https://home.vkshop.workers.dev/api/gateway/config

# API products check
curl -i https://home.vkshop.workers.dev/api/products
```
