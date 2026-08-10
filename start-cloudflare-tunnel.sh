#!/bin/bash
# /web/start-cloudflare-tunnel.sh -- Start Cloudflare Tunnel for frank-escudero.com
# Run after Reflex app is up on localhost:8000

set -euo pipefail

LOG=/var/log/cloudflare-tunnel.log
TUNNEL_CONFIG=/web/cloudflare-tunnel.yml
CREDENTIALS_DIR=/web/.cloudflared

log() { echo "$(date '+%F %T') cloudflare-tunnel: $*" | tee -a "$LOG"; }

# Ensure credentials directory exists
mkdir -p "$CREDENTIALS_DIR"

# Check if tunnel credentials exist
if [[ ! -f "$CREDENTIALS_DIR/frank-escudero-cv.json" ]]; then
    log "ERROR: Tunnel credentials not found at $CREDENTIALS_DIR/frank-escudero-cv.json"
    log "Run: cloudflared tunnel login"
    log "Then: cloudflared tunnel create frank-escudero-cv"
    log "Then: cloudflared tunnel route dns frank-escudero-cv frank-escudero.com"
    log "Then: cloudflared tunnel route dns frank-escudero-cv www.frank-escudero.com"
    exit 1
fi

# Wait for Reflex app to be ready
log "Waiting for Reflex app on localhost:8000..."
for i in {1..30}; do
    if curl -sf http://localhost:8000/_health >/dev/null 2>&1; then
        log "Reflex app is ready"
        break
    fi
    sleep 2
done

# Start the tunnel
log "Starting Cloudflare Tunnel..."
exec cloudflared --config "$TUNNEL_CONFIG" tunnel run frank-escudero-cv >>"$LOG" 2>&1