#!/bin/bash
# Manual, one-shot opencode run. Just delegates to opencode-worker.sh with a
# custom prompt and skips the site verify, so you can smoke-test a model
# without it editing/committing or restarting the website.
#   start->run->close, hard TIMEOUT_MINUTES cap, prints RESULT=... and exits
#   with the worker's code (0 ok / 1 error / 2 timeout / 3 site-down).
# Usage:  ./run-opencode-manual.sh [PROMPT]
# Env:    OPENCODE_WORKER_NOVERIFY is already set here (no website touch).
export OPENCODE_WORKER_NOVERIFY=1
exec /web/opencode-worker.sh "${1:-Improve this app or ecosystem looking for Todo.md files or find a task yourself, do it, reflect on an improvement and leave it in a Todo.md if not already there. This website will be a Reflex python framework CV website, for data of a person that will be added later.}"