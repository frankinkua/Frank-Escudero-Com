#!/bin/bash
LOG=/var/log/websiteserver.log

log() { echo "$(date '+%F %T') bootstrap: $*" >>"$LOG"; }

log "run"

if ! pgrep -x tailscaled >/dev/null; then
    log "starting tailscaled"
    /usr/sbin/tailscaled --state=/var/lib/tailscale/tailscaled.state --socket=/run/tailscale/tailscaled.sock --port=41641 >>"$LOG" 2>&1 &
    for _ in $(seq 1 30); do
        /usr/bin/tailscale status >/dev/null 2>&1 && break
        sleep 1
    done
else
    log "tailscaled already running"
fi

if /usr/bin/tailscale status >/dev/null 2>&1; then
    log "tailscale up"
else
    log "tailscale NOT up"
fi

if ! pgrep -x cron >/dev/null; then
    log "starting cron"
    service cron start >>"$LOG" 2>&1
else
    log "cron already running"
fi

/etc/init.d/websiteserver start >>"$LOG" 2>&1