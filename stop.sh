#!/bin/bash
cd "$(dirname "$0")"
npx pm2 delete kiosk-backend kiosk-frontend 2>/dev/null
echo "Kiosk stopped."
