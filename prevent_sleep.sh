#!/bin/bash
set -e

echo "=================================================="
echo "  Configuring Linux PC / Server for Always-On 24/7"
echo "=================================================="

# 1. User-level GNOME Power Management (disabling idle timeout & suspend)
echo "[1/3] Applying GNOME Desktop user power settings..."
if command -v gsettings >/dev/null 2>&1; then
    gsettings set org.gnome.settings-daemon.plugins.power sleep-inactive-ac-type 'nothing' 2>/dev/null || true
    gsettings set org.gnome.settings-daemon.plugins.power sleep-inactive-battery-type 'nothing' 2>/dev/null || true
    gsettings set org.gnome.settings-daemon.plugins.power sleep-inactive-ac-timeout 0 2>/dev/null || true
    gsettings set org.gnome.settings-daemon.plugins.power sleep-inactive-battery-timeout 0 2>/dev/null || true
    gsettings set org.gnome.desktop.session idle-delay 0 2>/dev/null || true
    echo " -> GNOME user sleep/idle settings disabled successfully."
fi

# Check if script has root privileges for systemd system-wide sleep masking
if [ "$EUID" -ne 0 ]; then
    echo ""
    echo "------------------------------------------------------------"
    echo " NOTICE: System-level changes (systemd / logind) require sudo."
    echo " Please re-run with sudo to disable system sleep targets:"
    echo "   sudo ./prevent_sleep.sh"
    echo "------------------------------------------------------------"
    exit 0
fi

# 2. Mask systemd sleep, suspend, hibernate, and hybrid-sleep targets
echo "[2/3] Masking systemd sleep & suspend targets..."
systemctl mask sleep.target suspend.target hibernate.target hybrid-sleep.target

# 3. Configure systemd-logind to ignore lid close and idle events
echo "[3/3] Configuring logind settings (/etc/systemd/logind.conf.d/disable-sleep.conf)..."
mkdir -p /etc/systemd/logind.conf.d/
tee /etc/systemd/logind.conf.d/disable-sleep.conf > /dev/null <<'EOF'
[Login]
HandleLidSwitch=ignore
HandleLidSwitchExternalPower=ignore
HandleLidSwitchDocked=ignore
IdleAction=ignore
EOF

echo "Reloading systemd-logind service..."
systemctl restart systemd-logind || systemctl reload systemd-logind || true

# 4. Disable UPower Lid Suspend (if installed)
if [ -f /etc/UPower/UPower.conf ]; then
    sed -i 's/^IgnoreLid=.*/IgnoreLid=true/' /etc/UPower/UPower.conf 2>/dev/null || true
fi

echo "=================================================="
echo "  SUCCESS! All system sleep and suspend targets disabled."
echo "  Your PC / Server will stay running 24/7 without sleeping."
echo "=================================================="
