#!/bin/bash
# Start dental kiosk (backend + frontend) with auto-detected LAN IP
set -e

cd "$(dirname "$0")"

# Auto-detect LAN IP
LAN_IP=$(ipconfig getifaddr en0 2>/dev/null || hostname -I 2>/dev/null | awk '{print $1}' || echo "localhost")
BACKEND_PORT=8000
FRONTEND_PORT=5173

echo "============================================"
echo "  All Nassau Dental Kiosk"
echo "============================================"
echo "  LAN IP:    $LAN_IP"
echo "  Backend:   http://$LAN_IP:$BACKEND_PORT"
echo "  Frontend:  http://$LAN_IP:$FRONTEND_PORT"
echo "  Kiosk URL: http://$LAN_IP:$FRONTEND_PORT"
echo "============================================"

# Set CORS to allow kiosk connections from LAN
export CORS_ORIGINS="http://$LAN_IP:$FRONTEND_PORT,http://localhost:$FRONTEND_PORT,https://$LAN_IP:$FRONTEND_PORT"
export LOG_LEVEL="${LOG_LEVEL:-INFO}"

# Build frontend with backend URL baked in
echo "[1/3] Building frontend..."
cd frontend
VITE_API_URL="http://$LAN_IP:$BACKEND_PORT" npm run build
cd ..

# Start with PM2 (kill ALL existing first to prevent duplicates)
echo "[2/3] Starting services..."
npx pm2 kill 2>/dev/null || true
npx pm2 start ecosystem.config.cjs

echo "[3/3] Ready!"
echo ""
echo "Open on kiosk: http://$LAN_IP:$FRONTEND_PORT"
echo ""
npx pm2 logs --lines 5
