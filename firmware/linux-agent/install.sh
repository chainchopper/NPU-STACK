#!/bin/bash
# Nirvana Agent — Quick installer for Linux edge devices
# Run: curl -sSL http://YOUR_INTELLIFY_IP:9090/agent/install.sh | bash

set -e

AGENT_DIR="/opt/nirvana-agent"
AGENT_PORT="${NIRVANA_AGENT_PORT:-9200}"

echo "╔══════════════════════════════════════════╗"
echo "║   Nirvana Edge Agent Installer v0.1.0    ║"
echo "╚══════════════════════════════════════════╝"
echo ""

# Create directory
sudo mkdir -p "$AGENT_DIR"

# Copy agent
sudo cp nirvana_agent.py "$AGENT_DIR/"
sudo cp nirvana-agent.service /etc/systemd/system/

# Install dependencies
echo "[1/3] Installing Python dependencies..."
pip3 install --quiet flask zeroconf psutil 2>/dev/null || \
    sudo pip3 install --quiet flask zeroconf psutil

# Detect NPU type and install runtime
echo "[2/3] Detecting NPU hardware..."
NPU_TYPE="cpu"

if [ -e /dev/rknpu ] || [ -e /sys/class/misc/rknpu ]; then
    NPU_TYPE="rknn"
    echo "  → Rockchip RKNN NPU detected"
    # rknn-lite2 usually pre-installed on Rockchip Linux images
fi

if command -v hailortcli &>/dev/null; then
    NPU_TYPE="hailo"
    echo "  → Hailo NPU detected"
fi

if [ -e /dev/apex_0 ]; then
    NPU_TYPE="coral"
    echo "  → Google Coral Edge TPU detected"
fi

if [ "$NPU_TYPE" = "cpu" ]; then
    echo "  → No NPU detected — CPU-only mode"
fi

# Update service environment
sudo sed -i "s/NIRVANA_NPU_TYPE=auto/NIRVANA_NPU_TYPE=$NPU_TYPE/" /etc/systemd/system/nirvana-agent.service

# Enable and start service
echo "[3/3] Starting agent service..."
sudo systemctl daemon-reload
sudo systemctl enable nirvana-agent
sudo systemctl start nirvana-agent

echo ""
echo "✅ Nirvana Agent installed and running!"
echo "   Health:  http://$(hostname -I | awk '{print $1}'):$AGENT_PORT/api/health"
echo "   mDNS:    $(hostname)._nirvana-npu._tcp.local."
echo ""
echo "   Manage:  sudo systemctl [start|stop|restart|status] nirvana-agent"
echo "   Logs:    sudo journalctl -u nirvana-agent -f"
