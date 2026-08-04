#!/bin/bash
# /web/bootstrap.sh -- boot entrypoint (cron @reboot + manual).
# Delegates ALL service startup (tailscaled with -no-logs-no-support so the
# state-dir log can never balloon to 49GB again, dbus, xrdp, cron, ollama(frank),
# Reflex websiteserver) to the single idempotent /usr/local/bin/start-rdp-server.sh
# so there is exactly one source of truth for boot ordering and logging.
# NOTE: the opencode-worker is intentionally NOT started here (it is an infinite
# edit loop); start it by hand with: /etc/init.d/opencode-worker start

LOG=/var/log/websiteserver.log
log() { echo "$(date '+%F %T') bootstrap: $*" >>"$LOG"; }
log "run -> /usr/local/bin/start-rdp-server.sh"
/usr/local/bin/start-rdp-server.sh >>"$LOG" 2>&1
log "done"
log "tailscale up" ; /usr/bin/tailscale status >/dev/null 2>&1 || log "tailscale NOT up"
log "cron up" ; pgrep -x cron >/dev/null && log "cron already running" || log "cron missing"