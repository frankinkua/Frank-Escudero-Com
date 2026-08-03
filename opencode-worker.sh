#!/bin/bash
CONF=/web/opencode-worker.conf
OPENCODE=/home/frank/.opencode/bin/opencode
WORKDIR=/web

log() { echo "$(date '+%F %T') worker: $*" >>"${LOG_FILE:-/var/log/opencode-worker.log}"; }

while true; do
    . "$CONF"
    if [ "${ENABLED:-1}" != "1" ]; then
        sleep 60
        continue
    fi
    if [ -n "$MAX_RUNS" ] && [ "$MAX_RUNS" -gt 0 ] && [ "${RUNS:-0}" -ge "$MAX_RUNS" ]; then
        log "MAX_RUNS ($MAX_RUNS) reached, exiting"
        exit 0
    fi
    RUNS=$((RUNS + 1))

    log "run $RUNS start (model=$MODEL)"

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

    timeout "$((TIMEOUT_MINUTES * 60))" "$OPENCODE" run --dir "$WORKDIR" -m "$MODEL" "${OPTS[@]}" "$PROMPT" >>"${LOG_FILE:-/var/log/opencode-worker.log}" 2>&1
    RC=$?

    ok=1
    if [ -n "$VERIFY_URL" ]; then
        if curl -fsS -m 20 -o /dev/null "$VERIFY_URL" 2>>"${LOG_FILE:-/var/log/opencode-worker.log}"; then
            log "run $RUNS done (rc=$RC), site OK"
        else
            ok=0
            log "run $RUNS done (rc=$RC), SITE DOWN -> rolling back"
            git -C "$WORKDIR" checkout -- . 2>>"${LOG_FILE:-/var/log/opencode-worker.log}"
            git -C "$WORKDIR" clean -fd 2>>"${LOG_FILE:-/var/log/opencode-worker.log}"
            /etc/init.d/websiteserver restart >>"${LOG_FILE:-/var/log/opencode-worker.log}" 2>&1
        fi
    else
        log "run $RUNS done (rc=$RC)"
    fi

    if [ "$ok" = "1" ] && [ "${GIT_COMMIT:-1}" = "1" ]; then
        git -C "$WORKDIR" add -A 2>>"${LOG_FILE:-/var/log/opencode-worker.log}"
        git -C "$WORKDIR" -c user.name=opencode-worker -c user.email=opencode-worker@local commit -m "opencode-worker run $RUNS" >>"${LOG_FILE:-/var/log/opencode-worker.log}" 2>&1
        log "run $RUNS committed"
    fi

    log "run $RUNS finished, sleeping ${INTERVAL_MINUTES}m"
    sleep "$((INTERVAL_MINUTES * 60))"
done
