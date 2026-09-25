# E-Commerce Server Management & Service Operations Guide

This guide provides step-by-step instructions on how to restart all background services, apply code modifications, verify service statuses, and monitor live application logs for the **E-Commerce Application (E-COM)**.

---

## 🚀 1. Quick One-Command Full Restart & Deployment

After making any code changes, dependency updates, or configuration modifications, you can apply everything and restart all server components with a single command:

```bash
cd /home/vasanth-v/Desktop/E-COM
bash deploy_autostart.sh
```

### What this script automatically does:
1. Clears any lingering processes on port `5000`.
2. Activates the Python virtual environment (`venv`) and updates packages from `requirements.txt`.
3. Reloads and updates the systemd service (`ecom.service`).
4. Restarts the E-Commerce web application server.
5. Restarts the Cloudflare Tunnel (`cloudflared`) to ensure external accessibility.
6. Prints out live service statuses and diagnostic health output.

---

## 🔄 2. Managing Individual Services

If you only need to restart or control specific services without running full deployment:

### A. E-Commerce Web Application (`ecom.service`)
- **Restart Application:**
  ```bash
  sudo systemctl restart ecom.service
  ```
- **Stop Application:**
  ```bash
  sudo systemctl stop ecom.service
  ```
- **Start Application:**
  ```bash
  sudo systemctl start ecom.service
  ```

### B. Redis Cache & Session Store (`redis-server`)
- **Restart Redis:**
  ```bash
  sudo systemctl restart redis-server
  ```
- **Check Redis Status:**
  ```bash
  sudo systemctl status redis-server
  ```

### C. Cloudflare Tunnel (`cloudflared`)
- **Restart Cloudflare Tunnel:**
  ```bash
  sudo systemctl restart cloudflared
  ```
- **Check Tunnel Status:**
  ```bash
  sudo systemctl status cloudflared
  ```

### D. Nginx Reverse Proxy (If active)
- **Test Configuration Syntax:**
  ```bash
  sudo nginx -t
  ```
- **Reload Nginx (Zero Downtime):**
  ```bash
  sudo systemctl reload nginx
  ```
- **Restart Nginx:**
  ```bash
  sudo systemctl restart nginx
  ```

---

## 📊 3. Checking Service Statuses

### Check All Core Services in One Command
```bash
sudo systemctl status ecom redis-server cloudflared --no-pager
```

### Check Active Listening Ports
To verify that the application and Redis are bound and listening on ports `5000` and `6379`:
```bash
sudo netstat -tulpn | grep -E '5000|6379'
```
*Or using `ss`:*
```bash
sudo ss -tulpn | grep -E '5000|6379'
```

### Quick HTTP Health Check
Verify that the server is responding to HTTP requests locally:
```bash
curl -I http://127.0.0.1:5000/
```
*(Expected response: `HTTP/1.1 200 OK` or `HTTP/1.1 302 FOUND`)*

---

## 📜 4. Monitoring Live Logs

### Systemd Service Live Logs (Real-time stream)
To follow live application stdout/stderr logs:
```bash
sudo journalctl -u ecom.service -f
```

### View Last 100 Log Lines
```bash
sudo journalctl -u ecom.service -n 100 --no-pager
```

### Application File Logs
Application-level logs are stored in the project `logs/` directory:
- **App Log:** `/home/vasanth-v/Desktop/E-COM/logs/app.log`
- **Gunicorn Error Log:** `/home/vasanth-v/Desktop/E-COM/logs/gunicorn_error.log`

To monitor app logs in real time:
```bash
tail -f /home/vasanth-v/Desktop/E-COM/logs/app.log
```

---

## 🛠️ 5. Standard Deployment Workflow After Code Modifications

Follow this workflow whenever you pull new code or edit files:

```bash
# Step 1: Navigate to project directory
cd /home/vasanth-v/Desktop/E-COM

# Step 2: (Optional) Pull latest code if using git
# git pull origin main

# Step 3: Install any newly added Python packages
source venv/bin/activate
pip install -r requirements.txt

# Step 4: Restart application service
sudo systemctl restart ecom.service

# Step 5: Verify service health
sudo systemctl status ecom.service --no-pager
curl -I http://127.0.0.1:5000/
```

---

## 🚨 6. Troubleshooting Common Issues

### Issue 1: Port 5000 is already in use
If port `5000` is blocked by an orphaned process:
```bash
sudo fuser -k 5000/tcp
sudo systemctl restart ecom.service
```

### Issue 2: Service fails to start after syntax error in code
1. Check the exact error line in `journalctl`:
   ```bash
   sudo journalctl -u ecom.service -n 50 --no-pager
   ```
2. Fix the syntax error in your Python code.
3. Restart the service:
   ```bash
   sudo systemctl restart ecom.service
   ```

### Issue 3: Database is empty or missing admin user
Run the database verification and seeder script using the virtual environment python:
```bash
cd /home/vasanth-v/Desktop/E-COM
./venv/bin/python seed.py
```

---

## 🌙 7. 24/7 Always-On Server Setup (Preventing PC / Server Sleep)

To guarantee that your server/PC never goes to sleep, hibernates, or suspends when idle or when laptop lid is closed:

### Quick 1-Step Execution
Run the included sleep prevention script with `sudo`:
```bash
cd /home/vasanth-v/Desktop/E-COM
sudo ./prevent_sleep.sh
```

### What `prevent_sleep.sh` Configures:
1. **GNOME Power Settings**: Sets `sleep-inactive-ac-type` to `'nothing'` and `idle-delay` to `0` (never turn off/sleep on idle).
2. **systemd Sleep Targets**: Masks `sleep.target`, `suspend.target`, `hibernate.target`, and `hybrid-sleep.target` system-wide.
3. **systemd logind (`/etc/systemd/logind.conf.d/disable-sleep.conf`)**: Configures `HandleLidSwitch=ignore` and `IdleAction=ignore` so closing the laptop lid or leaving the machine idle will not cause sleep.

