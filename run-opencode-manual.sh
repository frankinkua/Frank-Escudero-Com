#!/bin/bash
# Manual single-shot opencode run against LM Studio (no loop, no auto-commit).
# Use this to test a model/loading behavior before letting the cron worker loose.
# Usage:  ./run-opencode-manual.sh [PROMPT]
CONF=/web/opencode-worker.conf
OPENCODE=/home/frank/.opencode/bin/opencode
WORKDIR=/web
LOG=/var/log/opencode-manual.log

. "$CONF"

echo "model = $MODEL"
echo "url   = $URL"
echo "log   = $LOG"

PROMPT_ARG="${1:-$PROMPT}"

OPTS=()
[ "${AUTO_APPROVE:-1}" = "1" ] && OPTS+=(--auto)

export OPENCODE_CONFIG_CONTENT="$(python3 - "$URL" "${MODEL#*/}" <<'EOF'
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

echo "OPENCODE_CONFIG_CONTENT=$OPENCODE_CONFIG_CONTENT"
echo "--- running opencode, ctrl-c to abort ---"
"$OPENCODE" run --dir "$WORKDIR" -m "$MODEL" "${OPTS[@]}" "$PROMPT_ARG" 2>&1 | tee -a "$LOG"
echo "--- opencode exit: $? ---"