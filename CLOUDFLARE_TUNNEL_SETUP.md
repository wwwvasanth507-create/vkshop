# Cloudflare Tunnel Setup Guide for VKShop on Local Ubuntu Server

This document provides inch-by-inch, step-by-step instructions for connecting your **Local Ubuntu Server** running VKShop to a free **Cloudflare Tunnel** (`cloudflared`).

Cloudflare Tunnel creates an encrypted outbound HTTPS tunnel from your local server to Cloudflare's global edge network. This allows your website to be publicly accessible at your custom domain (e.g. `https://vkshop.yourdomain.com`) with automatic SSL, DDoS protection, and zero open inbound router ports.

---

## 🛠️ Step 1: Install `cloudflared` on Ubuntu Server

1. Download the official Debian/Ubuntu package:
   ```bash
   wget -q https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb
   ```

2. Install the package using `dpkg`:
   ```bash
   sudo dpkg -i cloudflared-linux-amd64.deb
   rm -f cloudflared-linux-amd64.deb
   ```

3. Verify installation:
   ```bash
   cloudflared --version
   ```

---

## 🔑 Step 2: Obtain Cloudflare Tunnel Token

1. Open [Cloudflare Zero Trust Dashboard](https://one.dash.cloudflare.com/).
2. Navigate to **Networks** $\rightarrow$ **Tunnels**.
3. Click **Add a Tunnel** $\rightarrow$ Select **Cloudflared**.
4. Enter tunnel name (e.g. `vkshop-ubuntu-tunnel`) and click **Save Tunnel**.
5. Choose **Debian / Ubuntu 64-bit** architecture.
6. Copy the command generated under **Install and run a connector**, which looks like:
   ```bash
   sudo cloudflared service install eyJhIjoiZ... (YOUR_UNIQUE_TUNNEL_TOKEN)
   ```

---

## 🚀 Step 3: Install & Connect Cloudflare Tunnel Service

Run the installation command on your Ubuntu terminal:

```bash
# Install cloudflared Systemd service using your unique tunnel token
sudo cloudflared service install <YOUR_CLOUDFLARE_TUNNEL_TOKEN>

# Enable and start the cloudflared service
sudo systemctl enable --now cloudflared

# Check tunnel status
sudo systemctl status cloudflared
```

---

## 🌐 Step 4: Route Public Domain to Local Nginx Server

1. In the Cloudflare Zero Trust Dashboard under **Public Hostnames**:
   - **Subdomain / Domain**: Enter your domain (e.g., `vkshop.yourdomain.com`).
   - **Service Type**: `HTTP`
   - **URL**: `127.0.0.1:80` (or `localhost:80` pointing to Nginx).
2. Click **Save Hostname**.

Cloudflare will automatically configure the DNS CNAME record and proxy public HTTPS traffic to your local Nginx server!

---

## 🏥 Step 5: Verification & Testing

1. Open your domain in browser:
   ```text
   https://vkshop.yourdomain.com
   ```
2. Test health probe endpoints:
   ```text
   https://vkshop.yourdomain.com/live
   https://vkshop.yourdomain.com/ready
   ```

3. View tunnel logs on Ubuntu:
   ```bash
   sudo journalctl -u cloudflared -f
   ```
