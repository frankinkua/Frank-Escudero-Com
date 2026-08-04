#!/bin/bash
# Single-shot opencode worker: start -> run -> close. NO loop, NO sleeping.
# Hard runtime cap (TIMEOUT_MINUTES); if the model runs longer it is killed.
# Prints a machine-readable RESULT line to stdout and exits with a distinct
# code so a caller (cron, a terminal, a wrapper) can self-check the outcome.
#
#   exit 0 = success (verified + committed)
#   exit 1 = model error / run failed, site fine
#   exit 2 = TIMEOUT: model killed after TIMEOUT_MINUTES
#   exit 3 = site DOWN after run -> rolled back + restarted
#
# Env override for probers: OPENCODE_WORKER_NOVERIFY=1 skips the site check.
CONF=/web/opencode-worker.conf
OPENCODE=/home/frank/.opencode/bin/opencode
WORKDIR=/web
LOG_FILE="${LOG_FILE:-/var/log/opencode-worker.log}"

log() { echo "$(date '+%F %T') worker: $*" >>"$LOG_FILE"; }

. "$CONF"
[ "${ENABLED:-1}" = "1" ] || { echo "RESULT=enabled=0"; exit 0; }

# Optional first arg overrides the conf PROMPT (handy for manual smoke tests).
if [ $# -gt 0 ]; then PROMPT="$1"; fi

echo "worker: model=$MODEL url=$URL timeout=${TIMEOUT_MINUTES}m"
log "run start (model=$MODEL)"

OPTS=()
[ "${AUTO_APPROVE:-1}" = "1" ] && OPTS+=(--auto)
if [ -n "$URL" ]; then
    SUFFIX="${MODEL#*/}"
    export OPENCODE_CONFIG_CONTENT="$(python3 - "$URL" "$SUFFIX" <<'EOF'
import json, sys
base, model = sys.argv[1], sys.argv[2]
print(json.dumps({
    "$schema": "https://opencode.ai/config.json",
    "provider": {
        "openai": {
            "options": {"baseURL": base + "/v1", "apiKey": "ollama"},
            "models": {model: {"name": model, "tool_call": True, "reasoning": True}},
        }
    },
}))
EOF
)"
fi

start_ts=$(date +%s)
timeout "$((TIMEOUT_MINUTES * 60))" "$OPENCODE" run --dir "$WORKDIR" -m "$MODEL" "${OPTS[@]}" "$PROMPT" 2>&1 | tee -a "$LOG_FILE"
RC=$?
elapsed=$(( $(date +%s) - start_ts ))

verdict="run"
if [ "$RC" -eq 124 ]; then
    echo "RESULT=timeout elapsed=${elapsed}s rc=${RC}"
    log "run TIMEOUT after ${elapsed}s"
    exit 2
elif [ "$RC" -ne 0 ]; then
    echo "RESULT=error rc=${RC}"
    log "run failed rc=${RC}"
    exit 1
fi

if [ "${OPENCODE_WORKER_NOVERIFY:-0}" = "1" ]; then
    echo "RESULT=ok-noverify elapsed=${elapsed}s rc=${RC}"
    log "run ok (verify skipped)"
    exit 0
fi

ok=1
if [ -n "$VERIFY_URL" ]; then
    if curl -fsS -m 20 -o /dev/null "$VERIFY_URL" 2>>"$LOG_FILE"; then
        log "run done (rc=$RC), site OK"
        echo "RESULT=ok elapsed=${elapsed}s rc=${RC}"
    else
        ok=0
        log "run done (rc=$RC), SITE DOWN -> rolling back"
        git -C "$WORKDIR" checkout -- . 2>>"$LOG_FILE"
        git -C "$WORKDIR" clean -fd 2>>"$LOG_FILE"
        /etc/init.d/websiteserver restart >>"$LOG_FILE" 2>&1
        echo "RESULT=site-down elapsed=${elapsed}s rc=${RC}"
        exit 3
    fi
else
    echo "RESULT=ok-noverify elapsed=${elapsed}s rc=${RC}"
    log "run ok (no VERIFY_URL)"
    exit 0
fi

if [ "${GIT_COMMIT:-1}" = "1" ]; then
    git -C "$WORKDIR" add -A 2>>"$LOG_FILE"
    echo "$PROMPT" >/dev/null
    if git -C "$WORKDIR" -c user.name=opencode-worker -c user.email=opencode-worker@local commit -m "opencode-worker run" >>"$LOG_FILE" 2>&1; then
        log "run committed"
    else
        log "nothing to commit"
    fi
fi

exit 0