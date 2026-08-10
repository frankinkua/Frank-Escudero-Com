# Chat button fix — investigation notes

## Problem
Clicking the chat FAB on `/` "does nothing" (no popup opens).

## Root-cause findings (verified)

### 1. WebSocket IS working — NOT the cause
Deployment: **grania (reflex) on :8000**, Tailscale Funnel proxies
`https://cv.story-tegu.ts.net` -> `http://127.0.0.1:8000`.

Tests run from this environment (Mon 10 Aug 2026 ~14:00 UTC):

- `GET http://127.0.0.1:8000/ping` -> `pong`; `/_health` -> `{"status":true}`.
- socket.io polling preflight `/_event/socket.io/?EIO=4&transport=polling` ->
  **400 "Invalid transport"** (confirms `TRANSPORT:websocket` only; polling disabled).
  BUT public Origin is reflected in CORS headers:
  `access-control-allow-origin: https://cv.story-tegu.ts.net` => host origin
  rewrite works, public origin accepted.
- True socket.io WS handshake
  `GET wss://cv.story-tegu.ts.net/_event/socket.io/?EIO=4&transport=websocket`
  -> **HTTP/1.1 101 Switching Protocols** (both local + public). 
- Raw (non-socket.io) `GET .../_event` -> 403 (socket.io rejects non-conforming
  upgrades; expected).

=> The websocket connection itself is functional for real clients. The earlier
403 conclusions were wrong (invalid raw-upgrade test).

### 2. LLM endpoint is down (operational issue, not the open-button cause)
`CHAT_URL="http://192.168.178.120:1234/v1"` (LM Studio LAN box) with
`timeout=httpx.Timeout(300.0)` (5 min). Server logs show
`openai.APIConnectionError`. The greeting/ask handlers fall back to `FALLBACK`,
but a 300s timeout can block the per-client event-handler queue: while a
`State.ask`/`greeting` generator is stuck awaiting openai, subsequent client
events (including `open_chat_popup`) queue behind it and won't execute until it
resolves or the socket drops (hence "Attempting to send delta to disconnected
client" in logs). Lowering the timeout is the fix.

### 3. Button logic itself is correct
- `open_chat_popup` (main.py:2044) is synchronous and trivial (sets
  `chat_popup_open=True`). No LLM.
- `load_home` (2365) does NOT call the LLM; only restores session, records visit,
  loads settings, picks suggestions, schedules JS polls.
- FAB `on_click=State.open_chat_popup` (main.py:3099); popup shown when
  `State.chat_popup_open` (3055). `CHAT_POPUP_JS` click-outside handler does not
  prevent opening (FAB click -> clickedFab truthy -> no close).

## Root cause (CONFIRMED)
- `load_home` schedules `rx.call_script(BROWSER_INFO_JS, callback=State.on_browser_info)`
  (main.py:2394). `on_browser_info` is an async GENERATOR (has `yield` at 2671 and
  2880) that runs ON PAGE LOAD for first-time visitors.
- It `await`s `client.chat.completions.create(..., stream=True)` (main.py:2858).
  The openai client used `httpx.Timeout(300.0)` (5 min). LM Studio at
  `192.168.178.120:1234` is unreachable (curl times out), so the connect attempt
  hangs up to ~300s before raising `APIConnectionError`.
- Reflex processes a given client's events SEQUENTIALLY. So while the greeting
  generator is stuck awaiting the dead LLM (~5 min), the visitor's click on the
  FAB (`on_click=State.open_chat_popup`) is queued behind it and never executes.
- When the client gives up (socket idle timeout), the generator later logs
  "Attempting to send delta to disconnected client". Both symptoms explained.

## Fix applied
- [x] Lowered openai timeout in `get_chat_client` (main.py:65):
  `httpx.Timeout(8.0, connect=3.0)`. On greeting/ask failure the code already
  falls back to the hardcoded `FALLBACK`/static greeting and sets
  `greeting_in_progress=False`, unblocking the client event queue within ~3-8s.
  (LM Studio is still down; the bot will reply with the fallback text until the
  LLM host is restored. That is Plan B and is the intended graceful degradation.)

## Status / conclusion
- WebSocket connectivity: OK (101 over public wss). Not the blocker.
- LLM endpoint (`192.168.178.120:1234`) down/unreachable from server.
- Fix in place: fast-fail timeout so page-load greeting no longer stalls the
  client event queue; popup FAB click can now run.

## Done
- [x] Verified websocket 101 over public `wss://cv.story-tegu.ts.net/_event/socket.io/`.
- [x] Confirmed origin/ host rewrite works (public Origin reflected).
- [x] Confirmed `open_chat_popup`/`load_home` don't touch the LLM.
- [x] Confirmed `CHAT_POPUP_JS` click-outside does not block opening.

## To do next
- [ ] **Fix the 300s openai timeout**: lower `httpx.Timeout(...)` to ~10-15s
      so a dead LM Studio box fails fast instead of blocking the event queue.
      (/web/main.py:65)
- [ ] Make greeting/ask handlers fail fast + robust (already try/except, but
      ensure no un-awaited long generator holds the queue).
- [ ] Restore LM Studio endpoint reachability (LAN box `192.168.178.120:1234`),
      OR point `CHAT_URL` to a reachable LLM.
- [ ] (Optional) Harden the click-outside JS to only act when popup is open and
      avoid firing `call_script("State.close_chat_popup")` on every outside click
      while closed (minor; not root cause).
- [ ] Real-browser re-test of the FAB after the timeout/LLM fix (no headless
      browser available in this env).

## Files touched
- `/web/main.py` (State class, chat handlers, JS strings).
- `/web/.web/env.json` + `reflex-env-*.js` (generated; ws endpoint baked in).
- `/web/CHAT_FIX_NOTES.md` (this file).

(Carry forward; do not delete.)
