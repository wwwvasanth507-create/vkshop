# High Availability Multi-Server E-commerce Platform
## Deployment and Connection Guide

This guide describes the complete step-by-step process of setting up the hardware connections and configuring the software services to deploy the Flask E-commerce platform on a highly available, multi-server network architecture.

---

## 1. Hardware Connection Flow (Step-by-Step)

Refer to the system connection topology diagrams for physical visual mapping:

### Part 1: Connect ISP Internet to Routers
1. **ISP Modems**: Connect the fiber/line cables from your ISP modems/ONTs to the separate WAN ports (WAN1, WAN2, WAN3... WAN N) on both the **Main Router** and the **Backup Router** (TP-Link ER8411).
2. **Power ON**: Connect power adapters and power on both routers. Wait for all WAN LEDs to stabilize.

### Part 2: Connect Routers to Core Managed Switch
3. **Main Router Out**: Run a CAT6/CAT7 LAN cable from the **LAN OUT** port of the **Main Router** to any Gigabit port on the **Core Managed Switch** (e.g., 24/48 Port Core Switch).
4. **Backup Router Out**: Run a CAT6/CAT7 LAN cable from the **LAN OUT** port of the **Backup Router** to another Gigabit port on the **Core Managed Switch**.

### Part 3: Connect Server Nodes to Core Switch
5. **Web Servers (N nodes)**: Run LAN cables from each of your Web/App servers (e.g., Server 1: Ubuntu 24.04, Server 2: Windows 11, Server 3: Ubuntu 24.04... Server N: Windows 11) to available ports on the Core Switch.
6. **Database Servers**: Connect the **Primary DB Server** (PostgreSQL) and the **Replica DB Server** (PostgreSQL) to the Core Switch.
7. **Redis Server**: Connect the dedicated **Redis Server** (caching and session node) to the Core Switch.
8. **MinIO Cluster**: Connect all storage nodes of the **MinIO Distributed Storage Cluster** to the Core Switch.

### Part 4: Router WAN Failover Configuration
9. Log in to the router admin page (e.g., `192.168.0.1` for Main, `192.168.20.1` for Backup).
10. Setup Multi-WAN ports and enable Multi-WAN Load Balancing.
11. Enable **Link Backup/WAN Failover**. Set the Backup Router in "Hot Standby" mode to automatically take over if the Main Router goes down.
12. Point your public domain DNS records to your public static IP address.

---

## 2. Software Infrastructure Setup

All servers run identical code pulled from Git.

### Prerequisites

Ensure the following system packages are installed on their respective server nodes:

* **Web Servers**: Python 3.12, pip, virtualenv, and Nginx (for local reverse proxy).
* **Database Cluster**: PostgreSQL 16+ on both Primary and Replica nodes.
* **Redis Server**: Redis 7+ server.
* **MinIO Nodes**: MinIO server binaries configured in distributed mode.

---

### Step 1: Clone Repository and Install Python Dependencies
On **each** Web/App server, clone the repository and run:
```bash
# Clone the repository
git clone <your-repo-url> /var/www/ecom
cd /var/www/ecom

# Create virtual environment and install packages
python -m venv venv
source venv/bin/activate  # On Windows: .\venv\Scripts\activate
pip install -r requirements.txt
```

---

### Step 2: Environment configuration (`.env`)
Create a `.env` file in the root directory on **each** web server:
```ini
FLASK_ENV=production
FLASK_DEBUG=False
SECRET_KEY=9a3f8db11c97a4d33458efec34a984a9  # Generate a unique key per cluster

# PostgreSQL connection pool settings
DATABASE_URL=postgresql://ecom_user:SecurePassword@192.168.10.30:5432/ecommerce

# Session Type: 'redis' routes session memory to the shared cluster
SESSION_TYPE=redis
REDIS_URL=redis://192.168.10.40:6379/0

# Shared Object Storage Settings (MinIO Cluster)
MINIO_ENDPOINT=192.168.10.50:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadminsecret
MINIO_BUCKET_NAME=ecom-uploads
MINIO_SECURE=False

# Global Settings
ADMIN_UPI_ID=admin@upi
SUPPORT_OFFICIAL_EMAIL=support@vkshop.com
```

---

### Step 3: Initialize and Seed PostgreSQL Database
Ensure your Primary PostgreSQL server is running and accessible. Then run the seeder from **one** of the web server nodes (the seeder will drop tables, recreate the schema, run adaptive column migrations, and load default data):
```bash
python seed.py
```
This automatically:
1. Creates the tables and registers the PostgreSQL schemas.
2. Seeds default admin (`admin`), seller (`seller`), and customer (`customer`) accounts.
3. Synchronizes mock product images and static banners to the MinIO cluster.

---

### Step 4: Configure Nginx Load Balancer
On the dedicated Load Balancer node (or the server where Nginx binds the public static IP), replace `/etc/nginx/nginx.conf` with the template included in the project:
```nginx
# Use nginx.conf from the project repository
# Update the upstream block with your server node IPs:
upstream ecom_servers {
    server 192.168.10.11:5000 max_fails=3 fail_timeout=15s; # Ubuntu Web Server 1
    server 192.168.10.12:5000 max_fails=3 fail_timeout=15s; # Ubuntu Web Server 2
    server 192.168.10.21:5000 max_fails=3 fail_timeout=15s; # Windows Web Server 1
}
```
Reload Nginx config:
```bash
sudo nginx -s reload
```

---

### Step 5: Start Production Web Services

#### On Ubuntu Nodes:
We run the application using `gunicorn` with the configuration provided in `gunicorn.conf.py`:
```bash
gunicorn -c gunicorn.conf.py app:app
```

#### On Windows Nodes:
We run the application using the multi-threaded `waitress` entry point `run_production.py`:
```bash
python run_production.py
```

---

## 3. High Availability Features

### A. Shared Object Storage (MinIO S3)
* Files uploaded to the application (product images, seller documents, Aadhaar scans, transaction proofs) bypass the local server storage.
* Werkzeug's `FileStorage.save` is transparently monkeypatched to stream directly to MinIO.
* Frontend templates dynamically route images through `/static/uploads/<path:filename>`, which is served directly from MinIO with fallback to local files in case S3 is temporarily unreachable.

### B. Redis Shared Sessions & Distributed Lock
* All server nodes share the same Redis instance for session state. If Nginx shifts a user from Server A to Server B, they remain logged in seamlessly.
* APScheduler background jobs (low stock alerts, auto-cancellations) use a Redis-based distributed lock (`lock:auto_cancel_orders`, etc.). Only **one** web node will execute a job at any given time, preventing race conditions or duplicate notifications.

### C. Live Health Check Endpoint
* The Nginx proxy uses passive health checks to monitor the server pool.
* A live `/health` endpoint is available to check database, Redis, and S3 status dynamically:
  ```bash
  curl http://localhost:5000/health
  ```
  Returns:
  ```json
  {
    "status": "healthy",
    "database": "connected",
    "redis": "connected",
    "minio": "connected"
  }
  ```
