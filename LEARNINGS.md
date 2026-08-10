# Learnings & Improvements

## Session: Chat Backend Resilience & Server Stability

### What was done
1. Made chat backend configurable via environment variables (`CHAT_URL`, `CHAT_API_KEY`, `CHAT_MODEL`, `CHAT_ENABLED`)
2. Added graceful fallback when AI chat is disabled or misconfigured (`get_chat_client()` returns `None`)
3. Fixed ntfy notification titles (service rejects emoji in titles - strip them)
4. Fixed Python indentation errors in greeting generation try/except blocks
5. Added `cron_improve.py` for self-improving content analysis
6. Added `site_store.py` for conversation persistence
7. Restarted the server and verified it's online

### Key Learnings

1. **ntfy.sh rejects emoji in titles** - The notification service returns errors when emoji characters are included in the `Title` header. Always strip emoji from notification titles.

2. **Defensive coding for optional services** - When external services (like LM Studio) might be unavailable, always check for `None` client before making API calls. Provide meaningful fallback messages.

3. **Environment variables for configuration** - Hardcoded URLs and API keys make the system fragile. Use `os.environ.get()` with sensible defaults for all external service configuration.

4. **Reflex framework quirks** - The Reflex web framework has specific requirements for string literals and indentation. Syntax errors can manifest far from their actual location.

5. **Server management without systemd** - This system uses a custom init script at `/etc/init.d/websiteserver` instead of systemd. Always check for existing init scripts before attempting to manage services.

6. **Indentation matters in Python** - A single missing indentation level in a try/except block causes `IndentationError`. When doing bulk edits with scripts, verify the result compiles.

### Improvements Made
- Graceful degradation when AI is disabled (visitors still get greeted, just with static messages)
- Configurable chat backend (easy to switch models or disable entirely)
- Self-improving cron job analyzes visitor conversations and proposes content fixes
- Persistent conversation storage for analytics
- Better error notifications (no more emoji-related failures)

### Server Status
- Local: http://localhost:8000 - **ONLINE** (HTTP 200)
- External: https://frank.codestudio.li - depends on tailscale/DNS

### Files Modified
- `main.py` - Core chat backend resilience
- `site_store.py` - New conversation persistence layer
- `cron_improve.py` - New self-improving cron job
- `prompt.md` - Improved AI prompts
- `filter.md` - Content filtering rules
- `AGENTS.md` - Project guidelines
