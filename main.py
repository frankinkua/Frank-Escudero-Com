from __future__ import annotations

import json
import logging
import os
import pathlib
import random
import secrets
import subprocess
import threading
import time
import urllib.parse
from datetime import datetime, timedelta, timezone

import asyncio
import httpx
import reflex as rx
from openai import AsyncOpenAI
from zoneinfo import ZoneInfo

import notify
import site_store
from reflex_base.event import Event

logger = logging.getLogger("web")
logger.setLevel(logging.INFO)
if not logger.handlers:
    _console = logging.StreamHandler()
    _console.setLevel(logging.INFO)
    logger.addHandler(_console)
WEB = pathlib.Path("/web")
DEFAULT_HOME_TITLE = "Agentic Generated Self-Hosted AI Webserver"
# Remote OpenAI-compatible endpoint: the olla LLM proxy on `gx10-23ef`
# (spark, 100.100.1.10), port 40114. No auth token required. Reachable over
# Tailscale only (not the LAN).
CHAT_URL = os.environ.get("CHAT_URL", "http://100.100.1.10:40114/olla/proxy/v1")
CHAT_API_KEY = os.environ.get("CHAT_API_KEY", "olla")
CHAT_MODEL = os.environ.get("CHAT_MODEL", "prism-ml/bonsai-27b")
CHAT_ENABLED = os.environ.get("CHAT_ENABLED", "1") == "1"
chat_client: AsyncOpenAI | None = None


def get_chat_client() -> AsyncOpenAI | None:
    global chat_client
    if not CHAT_ENABLED:
        return None
    if chat_client is None:
        chat_client = AsyncOpenAI(
            base_url=CHAT_URL,
            api_key=CHAT_API_KEY,
            # Fail fast when the LLM host is unreachable so an in-flight greeting/ask
            # can't stall a client's event queue (which blocks the chat FAB click).
            # A reachable local endpoint (Ollama) completes well within these limits.
            timeout=httpx.Timeout(60.0, connect=3.0),
        )
    return chat_client
FALLBACK = (
    "I couldn't formulate a reliable answer right now. "
    "The site is still a work in progress - ask again later."
)

# Example questions shown as clickable chips above the chat input. Two are
# picked at random per page load (see load_home). All are answerable from
# knowledge.md.
SUGGESTIONS = [
    "What does Frank do for a living?",
    "What tech stack does Frank use?",
    "How is this website hosted?",
    "What are Frank's most notable achievements?",
    "Who built and maintains this site?",
    "How can I contact Frank?",
    "How can I book a call with Frank?",
    "What's on Frank's CV?",
    "What is this site built with?",
    "Is this site secure?",
]

BG = "radial-gradient(ellipse at top, #1c2333, #0b0e14)"
CARD = {
    "padding": "2rem",
    "borderRadius": "0.9rem",
    "background": "#131826",
    "border": "1px solid #2a3247",
    "boxShadow": "0 12px 40px rgb(0 0 0 / .5)",
}
ACCENT = "#4ade80"
MUTED = "#66708a"

# --------------------------------------------------------------------------- #
# cv-light "girly" theme. Injected as a <style> + <script> in <head> for every
# page; every rule is gated behind `body.cv-light` so the default dark theme is
# untouched. The toggle (theme_toggle) flips that class (plus a `cv-light-page`
# marker on the page container) via client-side JS. No /web/assets writes.
# --------------------------------------------------------------------------- #
_WAND_SVG = (
    "<svg xmlns='http://www.w3.org/2000/svg' width='28' height='28' viewBox='0 0 28 28'>"
    "<path d='M4 25 L16 13 l3 3 L7 28 Z' fill='%238b5a2b'/>"
    "<path d='M16 13 l3 3 4 -2 -4 1 -1 -4 Z' fill='%23c56cf0'/>"
    "<path d='M20 4 l1.1 2.7 2.7 1.1 -2.7 1.1 -1.1 2.7 -1.1 -2.7 -2.7 -1.1 2.7 -1.1 Z' fill='%23ffd166'/>"
    "<path d='M10 6 l0.8 1.9 1.9 0.8 -1.9 0.8 -0.8 1.9 -0.8 -1.9 -1.9 -0.8 1.9 -0.8 Z' fill='%23ff9ff3'/>"
    "</svg>"
)
WAND_URI = "data:image/svg+xml;utf8," + urllib.parse.quote(_WAND_SVG, safe="%")

GIRLY_CSS = """/* cv-light girly theme: active only while <body> carries class cv-light */
body.cv-light{background:linear-gradient(180deg,#ffd9ec 0%,#ffeaf5 32%,#fff7ea 62%,#eaf9ff 100%) fixed}
body.cv-light .rt-Heading,
body.cv-light h1,
body.cv-light h2,
body.cv-light h3,
body.cv-light h4{color:#e0338c !important;animation:cvShimmer 3s ease-in-out infinite;-webkit-animation:cvShimmer 3s ease-in-out infinite}
body.cv-light .rt-Text{color:#7c2d62 !important}
body.cv-light .rt-Link,
body.cv-light a{color:#d63384 !important}
body.cv-light .radix-themes,
body.cv-light div.rt-Flex{background:transparent !important;border-color:rgba(255,105,180,.4) !important;box-shadow:none !important}
body.cv-light .rt-Box{background:rgba(255,255,255,.74) !important;border-color:#f5a9c9 !important;box-shadow:0 8px 26px rgba(255,105,180,.25) !important}
body.cv-light input,
body.cv-light textarea{background:#fff !important;color:#7c2d62 !important;border-color:#f5a9c9 !important}
body.cv-light .rt-BaseButton{background:linear-gradient(90deg,#ff9ff3,#ff6b81,#ffd166) !important;color:#fff !important;border-color:#f5a9c9 !important;text-shadow:0 1px 2px rgba(120,30,80,.3)}
body.cv-light .rt-BaseButton:hover{animation:cvWiggle .4s ease-in-out infinite;-webkit-animation:cvWiggle .4s ease-in-out infinite}
body.cv-light .rt-MenuContent .rt-Text{color:#e8ecf4 !important}
body.cv-light,body.cv-light *{cursor:url("@@WAND@@") 16 12,auto !important}
.cv-ic-light{display:none}
body.cv-light .cv-ic-dark{display:none}
body.cv-light .cv-ic-light{display:inline}
@keyframes cvShimmer{0%,100%{text-shadow:0 0 10px rgba(255,105,180,.6),0 0 22px rgba(255,209,102,.4)}50%{text-shadow:0 0 6px rgba(255,105,180,.35),0 0 14px rgba(255,209,102,.2)}}
@keyframes cvWiggle{0%,100%{transform:rotate(-2deg)}50%{transform:rotate(2deg)}}
@keyframes cvSlide{to{background-position:200% 0}}
@keyframes cvWash{0%{filter:hue-rotate(0)}100%{filter:hue-rotate(360deg)}}
@keyframes cvSway{0%,100%{transform:rotate(-8deg) translateY(0)}50%{transform:rotate(10deg) translateY(-8px)}}
@keyframes cvTwinkle{0%,100%{opacity:.35}50%{opacity:1}}
@keyframes cvFloat{0%{transform:translateY(0) translateX(0) rotate(0);opacity:0}8%{opacity:.95}100%{transform:translateY(-115vh) translateX(6vw) rotate(28deg);opacity:0}}
@keyframes cvRain{0%{transform:translateY(0) translateX(0) rotate(0);opacity:0}6%{opacity:.95}90%{opacity:.85}100%{transform:translateY(115vh) translateX(var(--cv-drift,0)) rotate(30deg);opacity:0}}
#cv-rain-layer{position:fixed;top:0;left:0;width:100%;height:100vh;z-index:9999;pointer-events:none;overflow:hidden}
@keyframes cvPop{0%{transform:scale(.2);opacity:1}70%{transform:scale(1.3);opacity:.8}100%{transform:scale(.4) translateY(14px);opacity:0}}
#cv-fun-overlay{position:fixed;inset:0;z-index:9998;pointer-events:none;overflow:hidden}
#cv-fun-overlay .cv-rainbow{position:absolute;top:0;left:0;right:0;height:14px;background:linear-gradient(90deg,#ff4d6d,#ffb703,#8ac926,#2dc6d6,#7b2ff7,#f72585,#ff4d6d);background-size:200% 100%;animation:cvSlide 4s linear infinite;-webkit-animation:cvSlide 4s linear infinite;box-shadow:0 0 18px rgba(255,105,180,.8)}
#cv-fun-overlay .cv-wash{position:absolute;inset:0;background:linear-gradient(115deg,rgba(255,0,110,.10),rgba(255,170,0,.12),rgba(120,255,120,.10),rgba(0,200,255,.12),rgba(180,0,255,.12));animation:cvWash 12s linear infinite;-webkit-animation:cvWash 12s linear infinite}
#cv-fun-overlay .cv-flowers span{position:absolute;font-size:26px;opacity:.85;animation:cvSway 5s ease-in-out infinite;-webkit-animation:cvSway 5s ease-in-out infinite;filter:drop-shadow(0 2px 6px rgba(255,105,180,.5))}
#cv-fun-overlay .cv-sparkles{position:absolute;inset:0;background:radial-gradient(2px 2px at 12% 22%,#fff,transparent),radial-gradient(3px 3px at 34% 68%,#ffd166,transparent),radial-gradient(2px 2px at 58% 12%,#ff9ff3,transparent),radial-gradient(3px 3px at 78% 44%,#54a0ff,transparent),radial-gradient(2px 2px at 90% 82%,#ff6b81,transparent),radial-gradient(2px 2px at 24% 90%,#fff,transparent),radial-gradient(3px 3px at 66% 30%,#c56cf0,transparent),radial-gradient(2px 2px at 46% 54%,#f6e58d,transparent);animation:cvTwinkle 3s ease-in-out infinite;-webkit-animation:cvTwinkle 3s ease-in-out infinite}
.cv-bubble{position:absolute;top:-10vh;left:0;z-index:1;pointer-events:none;animation:cvRain linear forwards;-webkit-animation:cvRain linear forwards;filter:drop-shadow(0 3px 8px rgba(255,105,180,.5))}
.cv-glitter{position:fixed;border-radius:50%;z-index:9999;pointer-events:none;animation:cvPop ease-out forwards;-webkit-animation:cvPop ease-out forwards}
@media print{#cv-fun-overlay{display:none !important}}
""".replace("@@WAND@@", WAND_URI)

THEME_JS = """(function () {
  if (typeof document === 'undefined') return;
  var L = 'cv-light';
  var EMOS = ['\\ud83c\\udf38','\\ud83d\\udc96','\\ud83e\\udd84','\\ud83c\\udf1f','\\ud83c\\udf08','\\ud83d\\udc9c','\\u2728','\\ud83d\\udc30','\\ud83c\\udf6d','\\ud83c\\udf80','\\ud83d\\udcab','\\ud83e\\uddc1','\\ud83d\\udc9d','\\u2601\\ufe0f'];
  var GCOL = ['#ff9ff3','#ffd166','#54a0ff','#ff6b81','#f6e58d','#c56cf0'];
  var bubbleTimer = null, glitterTimer = null, mx = null, my = null;
  var sensorOn = false, shakeAt = 0;
  var rainLayerEl = null, shakePeak = 0, shakeN = 0;
  function rainLayer() {
    if (rainLayerEl && document.body.contains(rainLayerEl)) return rainLayerEl;
    rainLayerEl = document.createElement('div');
    rainLayerEl.id = 'cv-rain-layer';
    document.body.appendChild(rainLayerEl);
    return rainLayerEl;
  }
  function buildOverlay() {
    var ov = document.getElementById('cv-fun-overlay');
    if (ov) return ov;
    ov = document.createElement('div');
    ov.id = 'cv-fun-overlay';
    var flowers = ['\\ud83c\\udf38','\\ud83c\\udf3a','\\ud83c\\udf3c','\\ud83d\\udcae','\\ud83c\\udf3f\\ufe0f','\\ud83c\\udf37','\\ud83c\\udf38','\\ud83c\\udf3a'];
    var spots = [[6,12],[88,16],[12,60],[90,68],[45,5],[4,86],[94,38],[70,92]];
    var fl = '', i;
    for (i = 0; i < flowers.length; i++) {
      fl += '<span style="left:' + spots[i][0] + '%;top:' + spots[i][1] + '%;animation-delay:' + (i * 0.6) + 's;-webkit-animation-delay:' + (i * 0.6) + 's">' + flowers[i] + '</span>';
    }
    ov.innerHTML = '<div class="cv-rainbow"></div><div class="cv-wash"></div><div class="cv-flowers">' + fl + '</div><div class="cv-sparkles"></div>';
    document.body.appendChild(ov);
    return ov;
  }
  function apply(mode) {
    var light = (mode === 'light');
    var b = document.body;
    if (!b) return;
    b.classList.toggle(L, light);
    if (light) {
      buildOverlay();
      startBubbles();
      startGlitter();
    } else {
      var ov = document.getElementById('cv-fun-overlay');
      if (ov) ov.remove();
      stopBubbles();
      stopGlitter();
    }
    try { localStorage.setItem('cv_theme', light ? 'light' : 'dark'); } catch (e) {}
  }
  window.cvToggleTheme = function () {
    apply(document.body.classList.contains(L) ? 'dark' : 'light');
  };
  window.cvSetTheme = function (m) { apply(m); };
  function spawnBubble() {
    if (document.querySelectorAll('.cv-bubble').length > 60) return;
    var s = document.createElement('span');
    s.className = 'cv-bubble';
    s.textContent = EMOS[(Math.random() * EMOS.length) | 0];
    s.style.left = (2 + Math.random() * 96) + '%';
    s.style.fontSize = (16 + Math.random() * 24) + 'px';
    s.style.setProperty('--cv-drift', (Math.random() * 12 - 6) + 'vw');
    s.style.animationDuration = (3 + Math.random() * 4) + 's';
    s.addEventListener('animationend', function () { s.remove(); });
    rainLayer().appendChild(s);
  }
  function startBubbles() {
    if (bubbleTimer) return;
    rainLayer();
    var i;
    for (i = 0; i < 12; i++) {
      (function (d) { setTimeout(spawnBubble, d); })(i * 110);
    }
    bubbleTimer = setInterval(spawnBubble, 130);
  }
  function stopBubbles() {
    if (bubbleTimer) { clearInterval(bubbleTimer); bubbleTimer = null; }
    var a = document.querySelectorAll('.cv-bubble'), i;
    for (i = 0; i < a.length; i++) a[i].remove();
    if (rainLayerEl && rainLayerEl.parentNode) rainLayerEl.parentNode.removeChild(rainLayerEl);
    rainLayerEl = null;
  }
  function onDeviceMotion(e) {
    var a = e.acceleration;
    if (!a) return;
    var mag = Math.abs(a.x || 0) + Math.abs(a.y || 0) + Math.abs(a.z || 0);
    shakePeak = Math.max(shakePeak, mag);
    shakeN++;
    if (shakeN > 2 && shakePeak > 17 && Date.now() - shakeAt > 1000 && document.body.classList.contains(L)) {
      shakeAt = Date.now();
      shakeN = 0; shakePeak = 0;
      if (navigator.vibrate) { try { navigator.vibrate([90, 40, 140, 40, 90]); } catch (err) {} }
      playWhimsy();
      var i;
      for (i = 0; i < 70; i++) {
        (function (d) {
          setTimeout(function () {
            var s = document.createElement('span');
            s.className = 'cv-bubble';
            s.textContent = EMOS[(Math.random() * EMOS.length) | 0];
            s.style.left = (Math.random() * 100) + '%';
            s.style.fontSize = (14 + Math.random() * 34) + 'px';
            s.style.setProperty('--cv-drift', (Math.random() * 22 - 11) + 'vw');
            s.style.animationDuration = (1.6 + Math.random() * 2.6) + 's';
            s.addEventListener('animationend', function () { s.remove(); });
            rainLayer().appendChild(s);
          }, d);
        })(i * 12);
      }
    }
    if (shakeN >= 5) { shakeN = 0; shakePeak = 0; }
  }
  var whimsy = null;
  function playWhimsy() {
    try {
      if (!whimsy) { whimsy = new Audio('/media/whimsy.wav'); whimsy.volume = 0.8; }
      whimsy.currentTime = 0;
      var p = whimsy.play();
      if (p && p.catch) { p.catch(function () {}); }
    } catch (err) {}
  }
  function enableSensors() {
    if (sensorOn) return;
    if (!('ontouchstart' in window) && !(navigator.maxTouchPoints > 0)) { sensorOn = true; return; }
    try { whimsy = new Audio('/media/whimsy.wav'); whimsy.volume = 0.8; whimsy.load(); } catch (err) {}
    var attach = function () {
      if (sensorOn) return;
      window.addEventListener('devicemotion', onDeviceMotion, true);
      sensorOn = true;
    };
    if (window.DeviceMotionEvent && DeviceMotionEvent.requestPermission) {
      DeviceMotionEvent.requestPermission().then(attach).catch(attach);
    } else {
      attach();
    }
  }
  window.addEventListener('touchstart', enableSensors, { passive: true });
  window.addEventListener('pointerdown', enableSensors, { passive: true });
  window.addEventListener('mousemove', function (e) { mx = e.clientX; my = e.clientY; }, { passive: true });
  function startGlitter() {
    if (glitterTimer) return;
    glitterTimer = setInterval(function () {
      if (mx == null) return;
      if (document.querySelectorAll('.cv-glitter').length > 60) return;
      var s = document.createElement('span');
      s.className = 'cv-glitter';
      var sz = 5 + Math.random() * 7;
      s.style.width = sz + 'px'; s.style.height = sz + 'px';
      s.style.left = (mx + (Math.random() * 30 - 15)) + 'px';
      s.style.top = (my + (Math.random() * 18 - 9)) + 'px';
      s.style.background = GCOL[(Math.random() * GCOL.length) | 0];
      s.style.animationDuration = (0.6 + Math.random() * 0.7) + 's';
      s.addEventListener('animationend', function () { s.remove(); });
      document.body.appendChild(s);
    }, 50);
  }
  function stopGlitter() {
    if (glitterTimer) { clearInterval(glitterTimer); glitterTimer = null; }
    var a = document.querySelectorAll('.cv-glitter'), i;
    for (i = 0; i < a.length; i++) a[i].remove();
  }
  function init() {
    var saved = 'dark';
    try { saved = localStorage.getItem('cv_theme') || 'dark'; } catch (e) {}
    apply(saved);
  }
  // Redirect old Tailscale domain to new canonical domain
  if (window.location.hostname.endsWith("cv.story-tegu.ts.net")) {
    window.location.replace("https://frank-escudero.com" + window.location.pathname + window.location.search);
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
"""

# Very soft "ding" played on the visitor's side at the end of every message.
# A single decaying sine through WebAudio (no asset); gain kept low on purpose.
# Autoplay policies mean the context must first be created/resumed after a user
# gesture, so we pre-warm it on the first pointer/touch interaction.
DING_JS = """
window.playDing = function() {
  try {
    var c = window.__cvDingCtx;
    if (!c) { c = window.__cvDingCtx = new (window.AudioContext || window.webkitAudioContext)(); }
    if (c.state === 'suspended') { c.resume(); }
    var t = c.currentTime;
    var o = c.createOscillator(), g = c.createGain();
    o.connect(g); g.connect(c.destination);
    o.type = 'sine';
    o.frequency.value = 1568;  // G6 — a polite, soft bell
    g.gain.setValueAtTime(0.0001, t);
    g.gain.exponentialRampToValueAtTime(0.06, t + 0.015);
    g.gain.exponentialRampToValueAtTime(0.0001, t + 0.30);
    o.start(t); o.stop(t + 0.32);
  } catch (e) {}
};
function __cvPreloadDing() {
  try {
    if (!window.__cvDingCtx) { window.__cvDingCtx = new (window.AudioContext || window.webkitAudioContext)(); }
    if (window.__cvDingCtx.state === 'suspended') { window.__cvDingCtx.resume(); }
  } catch (e) {}
  window.removeEventListener('pointerdown', __cvPreloadDing);
  window.removeEventListener('touchstart', __cvPreloadDing);
}
window.addEventListener('pointerdown', __cvPreloadDing, { passive: true });
window.addEventListener('touchstart', __cvPreloadDing, { passive: true });
"""

# Client-side probe: run once per page load, JSON-encodes what the browser
# tells us so the server can personalise the greeting. Fires via rx.call_script.
NOTIFY_JS = """
window.playBing = function() {
    if (document.hidden) {
        try {
            const ctx = new (window.AudioContext || window.webkitAudioContext)();
            const osc = ctx.createOscillator();
            osc.connect(ctx.destination);
            osc.frequency.value = 880;
            osc.start();
            osc.stop(ctx.currentTime + 0.1);

            if (!window.blinkInterval) {
                const orig = document.title;
                window.blinkInterval = setInterval(() => {
                    document.title = document.title === orig ? "New Message!" : orig;
                }, 1000);
                const clear = () => {
                    clearInterval(window.blinkInterval);
                    window.blinkInterval = null;
                    document.title = orig;
                    document.removeEventListener('visibilitychange', clear);
                };
                document.addEventListener('visibilitychange', clear);
            }
        } catch (e) {}
    }
};
"""

BROWSER_INFO_JS = (
    "(function(){"
    "let v=null;"
    "try{"
    "  v=localStorage.getItem('cv_visitor')||'';"
    "  if(!v){"
    "    v=(window.crypto&&crypto.randomUUID)?('v_'+crypto.randomUUID())"
    "      :('v_'+'xxxxxxxxxxxxxxxx'.replace(/x/g,function(){return ((Math.random()*16)|0).toString(16);})"
    "         +'-'+Date.now().toString(36));"
    "    if(v.indexOf('v_')!==0)v='v_'+v;"
    "    localStorage.setItem('cv_visitor',v);"
    "  }"
    "}catch(e){}"
    "return JSON.stringify({"
    "lang:navigator.language||'',"
    "langs:(navigator.languages||[]).join(','),"
    "tz:(Intl.DateTimeFormat().resolvedOptions().timeZone)||'',"
    "platform:navigator.platform||'',"
    "cores:navigator.hardwareConcurrency||0,"
    "mem:navigator.deviceMemory||0,"
    "online:navigator.onLine,"
    "now:Date.now(),"
    "screen:screen.width+'x'+screen.height,"
    "visitor:v,"
    "ua:navigator.userAgent||''"
    "});"
    "})()"
)

# Client-side self-perpetuating poll timer. Reflex's _call_script handler awaits
# promise-returning JS before firing the callback, so the resolved promise
# schedules the next tick. Used to auto-refresh the admin dashboard.
ADMIN_POLL_MS = 10_000
LIVE_CHAT_POLL_MS = 4_000
# Mirror the store transcript into the visitor's chat on `/` so admin edits and
# takeover replies reach them even if the instant push is skipped/missed.
VISITOR_CHAT_POLL_MS = 3_000

# Admin dashboard list pagination (threads + users).
ADMIN_PAGE_SIZE = 10

# Conversation compactor: once a thread's estimated token count passes this,
# the assistant summarises the whole thread and the summary becomes the history
# (so the model never has to reason over a bloated 80k+ token transcript).
COMPACT_TOKEN_THRESHOLD = 80_000


def auto_refresh_js(ms: int) -> str:
    return (
        "(async () => { await new Promise(r => setTimeout(r, " + str(ms) + ")); return 'tick'; })()"
    )

# Maps an IETF language tag (en-US, de, fr, nl, es...) to a spoken English name
# so the LLM can address the visitor in the right language even when the tag
# is ambiguous. Best-effort; unknown tags fall back to the raw code.
_LANG_NAMES = {
    "en": "English", "de": "German", "nl": "Dutch", "fr": "French",
    "es": "Spanish", "pt": "Portuguese", "it": "Italian", "pl": "Polish",
    "ru": "Russian", "tr": "Turkish", "sv": "Swedish", "no": "Norwegian",
    "da": "Danish", "fi": "Finnish", "hu": "Hungarian", "cs": "Czech",
    "ro": "Romanian", "bg": "Bulgarian", "uk": "Ukrainian", "el": "Greek",
    "he": "Hebrew", "ar": "Arabic", "fa": "Persian", "hi": "Hindi",
    "bn": "Bengali", "ja": "Japanese", "zh": "Chinese", "ko": "Korean",
    "th": "Thai", "vi": "Vietnamese", "id": "Indonesian", "ms": "Malay",
    "ca": "Catalan", "hr": "Croatian", "sk": "Slovak", "sl": "Slovenian",
    "lt": "Lithuanian", "lv": "Latvian", "et": "Estonian", "is": "Icelandic",
}


def detect_language(prefs: str) -> str:
    """Pick the visitor's best language from an Accept-Language string."""
    for part in prefs.split(","):
        tag = part.split(";")[0].strip().lower()
        if not tag or tag == "*":
            continue
        base = tag.split("-")[0]
        return _LANG_NAMES.get(base, base)
    return "English"


async def _geo_lookup(ip: str) -> dict[str, str]:
    """Best-effort public IP -> country/countryCode/city/lat/lon/timezone. Never raises."""
    if not ip or ip in {"127.0.0.1", "::1"}:
        return {}
    try:
        async with httpx.AsyncClient(timeout=3.0) as c:
            r = await c.get(
                f"http://ip-api.com/json/{ip}",
                params={"fields": "status,country,countryCode,regionName,city,lat,lon,timezone"},
            )
            d = r.json()
        if d.get("status") == "success":
            return {
                "country": d.get("country", ""),
                "country_code": d.get("countryCode", ""),
                "region": d.get("regionName", ""),
                "city": d.get("city", ""),
                "lat": d.get("lat", ""),
                "lon": d.get("lon", ""),
                "timezone": d.get("timezone", ""),
            }
    except Exception:  # noqa: BLE001
        pass
    return {}


# In-memory geo cache so repeat visits (and analytics) don't re-hit ip-api.com.
_GEO_CACHE: dict[str, dict[str, str] | None] = {}
_GEO_LOCK = threading.Lock()


async def _geo_for(ip: str) -> dict[str, str]:
    """Cached async geo lookup. Empty IPs and failures are cached too."""
    if not ip:
        return {}
    with _GEO_LOCK:
        if ip in _GEO_CACHE:
            return _GEO_CACHE[ip] or {}
    geo = await _geo_lookup(ip)
    with _GEO_LOCK:
        _GEO_CACHE[ip] = geo or None
    return geo


async def _enrich_visit(ip: str) -> None:
    """Background geo lookup for a just-recorded visit, then backfill older rows."""
    try:
        geo = await _geo_for(ip)
        site_store.backfill_geo(ip, geo)
    except Exception:  # noqa: BLE001
        logger.exception("visit geo enrichment failed")


def _real_client_ip(router) -> str:
    """Real visitor IP, honouring the Tailscale Funnel x-forwarded-for."""
    headers = router.headers
    raw = getattr(headers, "raw_headers", None) or {}
    forwarded = raw.get("x-forwarded-for") or raw.get("X-Forwarded-For") or ""
    return forwarded.partition(",")[0].strip() or router.session.client_ip or ""


def server_log_tail(lines: int = 40) -> str:
    try:
        return "\n".join(
            pathlib.Path("/var/log/websiteserver.log").read_text(errors="replace").splitlines()[-lines:]
        )
    except OSError:
        return "(no server log yet)"


# Fire-and-forget ntfy push (never delays the visitor's own request).
def _notify(title: str, message: str, tags: list[str] | None = None) -> None:
    try:
        asyncio.get_running_loop().create_task(notify.send(title, message, tags))
    except RuntimeError:
        pass


# Conversations we already pushed a "first message" notification for (per process).
_NOTIFIED_CONVS: set[str] = set()

# Live visitor chat sessions: conv_id -> {client_token: last_seen_epoch}. Used
# to push admin edits / takeover replies straight to the visitor's socket (the
# visitor-side poll is the fallback). In-memory + pruned; re-registered on each
# poll tick and visitor chat event.
_CONV_TOKENS: dict[str, dict[str, float]] = {}


def _register_visitor_token(conv_id: str, token: str) -> None:
    """Remember a visitor's live socket token so admin writes can push to them."""
    if not conv_id or not token:
        return
    now = time.time()
    entry = _CONV_TOKENS.setdefault(conv_id, {})
    entry[token] = now
    stale = [t for t, ts in entry.items() if now - ts > 600]
    if len(entry) > 8:
        stale += sorted(entry, key=entry.get)[: len(entry) - 8]
    for t in stale:
        entry.pop(t, None)


def _country_flag(country_code: str) -> str:
    """ISO 3166-1 alpha-2 -> flag emoji (regional indicator symbols)."""
    cc = (country_code or "").upper().strip()
    if len(cc) != 2 or not cc.isalpha():
        return ""
    return chr(0x1F1E6 + ord(cc[0]) - ord("A")) + chr(0x1F1E6 + ord(cc[1]) - ord("A"))


# Best-guess language -> flag emoji when the visitor's country is unknown.
_LANG_FLAGS = {
    "en": "🇬🇧", "de": "🇩🇪", "nl": "🇳🇱", "fr": "🇫🇷", "es": "🇪🇸", "pt": "🇵🇹",
    "it": "🇮🇹", "pl": "🇵🇱", "ru": "🇷🇺", "tr": "🇹🇷", "sv": "🇸🇪", "no": "🇳🇴",
    "da": "🇩🇰", "fi": "🇫🇮", "hu": "🇭🇺", "cs": "🇨🇿", "ro": "🇷🇴", "bg": "🇧🇬",
    "uk": "🇺🇦", "el": "🇬🇷", "he": "🇮🇱", "ar": "🇸🇦", "fa": "🇮🇷", "hi": "🇮🇳",
    "bn": "🇧🇩", "ja": "🇯🇵", "zh": "🇨🇳", "ko": "🇰🇷", "th": "🇹🇭", "vi": "🇻🇳",
    "id": "🇮🇩", "ms": "🇲🇾", "ca": "🇦🇩", "hr": "🇭🇷", "sk": "🇸🇰", "sl": "🇸🇮",
    "lt": "🇱🇹", "lv": "🇱🇻", "et": "🇪🇪", "is": "🇮🇸",
}


def _language_flag(lang: str) -> str:
    """Spoken language name (e.g. 'German') -> flag emoji, best-effort."""
    for code, name in _LANG_NAMES.items():
        if name == lang:
            return _LANG_FLAGS.get(code, "")
    return ""


# WMO weather codes -> (emoji, plain-word description).
_WMO = {
    0: ("☀️", "clear"),
    1: ("🌤️", "mostly sunny"),
    2: ("⛅", "partly cloudy"),
    3: ("☁️", "overcast"),
    45: ("🌫️", "foggy"),
    48: ("🌫️", "icy fog"),
    51: ("🌦️", "light drizzle"),
    53: ("🌦️", "drizzle"),
    55: ("🌧️", "heavy drizzle"),
    56: ("🌧️", "freezing drizzle"),
    57: ("🌧️", "freezing drizzle"),
    61: ("🌦️", "light rain"),
    63: ("🌧️", "rain"),
    65: ("🌧️", "heavy rain"),
    66: ("🌧️", "freezing rain"),
    67: ("🌧️", "freezing rain"),
    71: ("🌨️", "light snow"),
    73: ("🌨️", "snow"),
    75: ("❄️", "heavy snow"),
    77: ("🌨️", "snow grains"),
    80: ("🌦️", "light showers"),
    81: ("🌧️", "showers"),
    82: ("⛈️", "heavy showers"),
    85: ("🌨️", "snow showers"),
    86: ("🌨️", "heavy snow showers"),
    95: ("⛈️", "thunderstorm"),
     96: ("⛈️", "thunderstorm with hail"),
     99: ("⛈️", "thunderstorm with hail"),
}


# WMO codes that warrant a weather-warning mention to the visitor.
_WARNINGS = {
    56: "freezing drizzle",
    57: "freezing drizzle",
    66: "freezing rain",
    67: "freezing rain",
    65: "heavy rain",
    82: "heavy showers",
    86: "heavy snow showers",
    95: "thunderstorm",
    96: "thunderstorm with hail",
    99: "thunderstorm with hail",
}


def _weather_warning(code: object) -> str:
    """WMO weather code -> warning string, '' when nothing alarming."""
    try:
        return _WARNINGS.get(int(code), "")
    except (TypeError, ValueError):
        return ""


# Moon phase index -> (emoji, name). open-meteo reports 0=new .. 0.5=full .. 1=new.
_MOON = [
    ("🌑", "new moon"),
    ("🌒", "waxing crescent"),
    ("🌓", "first quarter"),
    ("🌔", "waxing gibbous"),
    ("🌕", "full moon"),
    ("🌖", "waning gibbous"),
    ("🌗", "last quarter"),
    ("🌘", "waning crescent"),
]


def _moon_phase(phase: object) -> tuple[str, str]:
    """open-meteo moon_phase (0..1) -> (emoji, name)."""
    try:
        p = float(phase)
    except (TypeError, ValueError):
        return "", ""
    idx = round(p * 8) % 8
    return _MOON[idx]


async def _weather_lookup(lat: str, lon: str) -> dict[str, str]:
    """Best-effort current weather + sun/moon times from open-meteo (no key). Never raises."""
    if not lat or not lon:
        return {}
    out: dict[str, str] = {}
    try:
        async with httpx.AsyncClient(timeout=3.0) as c:
            r = await c.get(
                "https://api.open-meteo.com/v1/forecast",
                params={
                    "latitude": lat,
                    "longitude": lon,
                    "current": (
                        "temperature_2m,apparent_temperature,relative_humidity_2m,"
                        "precipitation,pressure_msl,wind_speed_10m,weather_code,is_day"
                    ),
                    "timezone": "auto",
                },
            )
            d = r.json()
        cw = (d.get("current") or {})
        emoji, word = _WMO.get(cw.get("weather_code", -1), ("🌡️", "unknown"))
        temp = cw.get("temperature_2m")
        feels = cw.get("apparent_temperature")
        hum = cw.get("relative_humidity_2m")
        precip = cw.get("precipitation")
        press = cw.get("pressure_msl")
        wind = cw.get("wind_speed_10m")

        def _fmt(v: object, unit: str, plus: bool = False) -> str:
            """Format a numeric value to a short string ('22°C'), '' if missing."""
            try:
                f = float(v)  # type: ignore[arg-type]
            except (TypeError, ValueError):
                return ""
            return f"{f:+.0f}{unit}" if plus else f"{f:.0f}{unit}"

        out.update({
            "emoji": emoji,
            "word": word,
            "temp": _fmt(temp, "°C", plus=True),
            "feels_like": _fmt(feels, "°C", plus=True),
            "humidity": _fmt(hum, "%"),
            "precip": _fmt(precip, "mm"),
            "pressure": _fmt(press, "hPa"),
            "wind": _fmt(wind, "km/h"),
            "is_day": bool(cw.get("is_day", 1)),
            "warning": _weather_warning(cw.get("weather_code")),
        })
    except Exception:  # noqa: BLE001
        pass
    try:
        async with httpx.AsyncClient(timeout=3.0) as c:
            r = await c.get(
                "https://api.open-meteo.com/v1/forecast",
                params={
                    "latitude": lat,
                    "longitude": lon,
                    "daily": "sunrise,sunset,moon_phase",
                    "timezone": "auto",
                    "forecast_days": "1",
                },
            )
            d = r.json()
        day = (d.get("daily") or {})
        moon_emoji, moon_name = _moon_phase((day.get("moon_phase") or [None])[0])


        def _clock(v: object) -> str:
            """'2026-08-04T05:47' -> '05:47', else ''."""
            s = str(v or "")
            return s.split("T")[-1][:5] if "T" in s else s[:5]

        out.update({
            "sunrise": _clock((day.get("sunrise") or [""])[0]),
            "sunset": _clock((day.get("sunset") or [""])[0]),
            "moon": moon_name,
            "moon_emoji": moon_emoji,
        })
    except Exception:  # noqa: BLE001
        pass
    return out


def _time_of_day(hour: int) -> str:
    """Map a local 0-23 hour to a greeting phrase (for the LLM's flavour)."""
    if 5 <= hour < 12:
        return "morning"
    if 12 <= hour < 18:
        return "afternoon"
    if 18 <= hour < 22:
        return "evening"
    return "night"


def _git(cmd: list[str]) -> str:
    try:
        return subprocess.run(
            cmd, cwd=WEB, capture_output=True, text=True, check=True, timeout=3
        ).stdout.strip()
    except Exception:
        return ""


def app_version() -> str:
    """Short deploy version: APP_VERSION env, else '0.1.0 (<7-char git SHA>)' (no leading v)."""
    env_v = os.environ.get("APP_VERSION", "").strip()
    if env_v:
        return env_v.lstrip("v")
    sha = _git(["git", "rev-parse", "--short", "HEAD"])
    return f"0.1.0 ({sha})" if sha else "0.1.0"


def changelog_entries() -> list[tuple[str, str, str]]:
    """[(sha, iso-date, subject)] newest first, for the RSS feed."""
    log = _git(["git", "log", "--pretty=format:%h|%ci|%s", "-20"])
    out: list[tuple[str, str, str]] = []
    for row in (log or "").splitlines():
        sha, ci, subj = (row.split("|", 2) + ["", ""])[:3]
        out.append((sha, ci, subj))
    return out


def rss_xml() -> str:
    """Atom-ish RSS feed: site about/cv content (static) + git changelog (live)."""
    now = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")

    def _slug(text: str, n: int = 200) -> str:
        flat = " ".join(text.split())
        return flat[:n] + ("…" if len(flat) > n else "")

    changelog_items = "\n".join(
        f"<item><title>update {sha} — {subj}</title>"
        f"<link>https://frank-escudero.com/</link>"
        f"<guid>{sha}</guid><pubDate>{ci}</pubDate>"
        f"<description>Site update {sha}</description></item>"
        for sha, ci, subj in changelog_entries()
    )
    static_items = "\n".join(
        f"<item><title>{title}</title>"
        f"<link>https://frank-escudero.com/{link}</link>"
        f"<guid>{guid}</guid><pubDate>{now}</pubDate>"
        f"<description>{_slug(body)}</description></item>"
        for title, link, guid, body in (
            ("About Frank Escudero", "about", "about", read_doc("knowledge.md")),
            ("CV — Frank Escudero", "cv", "cv", read_doc("cv.md")),
            ("Projects — Frank Escudero", "projects", "projects", read_doc("projects.md")),
        )
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0"><channel>'
        "<title>Frank Escudero CV</title>"
        "<link>https://frank-escudero.com/</link>"
        "<description>Frank Escudero's self-hosted AI CV — content and site updates.</description>"
        f"{changelog_items}{static_items}</channel></rss>\n"
    )


def sitemap_xml() -> str:
    """Basic XML sitemap of all public pages, for crawlers."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    urls = [
        "", "/about", "/cv", "/projects", "/contact", "/appointments",
    ]
    entries = "\n".join(
        f"<url><loc>https://frank-escudero.com{u}/</loc>"
        f"<lastmod>{now}</lastmod><changefreq>weekly</changefreq></url>"
        for u in urls
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{entries}\n</urlset>\n"
    )


def app_updated() -> str:
    """Human-readable date the source last changed (git commit date, fallback file mtime)."""
    ci = _git(["git", "log", "-1", "--format=%ci"])
    if ci:
        try:
            dt = datetime.strptime(ci[:19], "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)
            return dt.strftime("%Y-%m-%d %H:%M %Z").replace(" UTC", "")
        except Exception:
            return ci[:19]
    try:
        ts = datetime.fromtimestamp((WEB / "main.py").stat().st_mtime, timezone.utc)
        return ts.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return "unknown"


VERSION_LABEL = app_version()
UPDATED_LABEL = app_updated()


def page_footer() -> rx.Component:
    """Persistent footer showing app version + last-updated date on every page."""
    return rx.hstack(
        rx.text(
            f"v{VERSION_LABEL}",
            fontSize="0.75rem",
            color="#64748b",
            fontFamily="ui-monospace, Menlo, monospace",
        ),
        rx.text(
            f"updated {UPDATED_LABEL}",
            fontSize="0.75rem",
            color="#64748b",
            fontFamily="ui-monospace, Menlo, monospace",
        ),
        rx.cond(
            State.is_admin,
            rx.link(
                "admin",
                href="/admin",
                fontSize="0.75rem",
                color="#64748b",
                fontFamily="ui-monospace, Menlo, monospace",
            ),
            rx.text("", fontSize="0.75rem"),
        ),
        justify="center",
        width="100%",
        padding="0.8rem",
        borderTop="1px solid #2a3247",
        opacity="0.7",
    )


# Where /appointments redirects (Google Calendar booking page).
APPOINTMENTS_URL = "https://calendar.google.com/calendar/u/0/appointments/AcZssZ0Cqg2mYA8lqoAsURaLim0pjczGu3fErFCYI20="

# The only picture in the repo — Frank with his horse. Served read-only via
# the /media/frank.png backend route (no /web/assets writes).
FRANK_PHOTO = pathlib.Path("/web/frank-escudero-raw-data/pictures/frank/cv-image-frank-with-his-horse.png")


def work_in_progress_banner() -> rx.Component:
    """Big 'work in progress' banner with Frank's photo below the text."""
    return rx.vstack(
        rx.text("WORK IN PROGRESS", color="#fca5a5", fontWeight="700", fontSize="1.1rem"),
        rx.image(
            src="/media/frank.png",
            alt="Frank Escudero with his horse",
            width="min(300px, 80vw)",
            height="auto",
            borderRadius="0.6rem",
            border="1px solid #2a3247",
        ),
        rx.text(
            "Disclaimer, the AI was trained by other AIs so my info is a photocopy of a "
            "photocopy of a photocopy. There are a lot of errors, but I'm testing a theory. -Frank",
            color=MUTED,
            fontSize="0.85rem",
            textAlign="center",
            fontStyle="italic",
        ),
        width="100%",
        background="#0f141f",
        border="1px solid #2a3247",
        borderRadius="0.6rem",
        padding="0.7rem 1rem",
        marginBottom="1.2rem",
        spacing="3",
        align="center",
    )


# Inline SVG favicon (no /web/assets writes — app-only). A small "FE" monogram.
FAVICON_SVG = (
    "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' "
    "viewBox='0 0 64 64'%3E%3Crect width='64' height='64' fill='%230b0e14'/"
    "%3E%3Ctext x='50%25' y='55' dominant-baseline='middle' text-anchor='middle' "
    "fill='%234ade80' font-family='monospace' font-size='30' font-weight='700'"
    "%3EFE%3C/text%3E%3C/svg%3E"
)


def parse_home_doc(source: str) -> tuple[str, str]:
    """Split home.md into (title, intro). A leading '# ' line is the H1; the
    rest is rendered as the intro paragraph. Files without it keep the title."""
    lines = source.splitlines()
    if lines and lines[0].startswith("# "):
        return lines[0][2:].strip(), "\n".join(lines[1:]).lstrip("\n")
    return DEFAULT_HOME_TITLE, source


def _default_home() -> tuple[str, str]:
    try:
        return parse_home_doc((WEB / "home.md").read_text())
    except OSError:
        return DEFAULT_HOME_TITLE, ""


_DEFAULT_HOME_TITLE, _DEFAULT_HOME_INTRO = _default_home()


def read_doc(name: str) -> str:
    try:
        return (WEB / name).read_text()
    except OSError:
        return f"<!-- missing {name} -->"


INCIDENT_LOG = read_doc("incident.md")


def incident_log() -> rx.Component:
    """Homepage incident writeup, rendered just above the footer."""
    return rx.vstack(
        rx.markdown(INCIDENT_LOG, color=MUTED, fontSize="0.8rem"),
        width="min(720px, 92vw)",
        padding="1rem",
        borderTop="1px solid #2a3247",
    )


def _human_size(n: int) -> str:
    if n >= 1024 * 1024:
        return f"{n / (1024 * 1024):.1f} MB"
    if n >= 1024:
        return f"{n / 1024:.1f} KB"
    return f"{n} B"


PUBLIC_DOCS = {"home.md", "knowledge.md", "cv.md", "contact.md", "projects.md"}


def list_editable_docs() -> list[dict[str, object]]:
    """File-manager list of markdown docs editable from the admin Pages tab."""
    docs: list[dict[str, object]] = []
    try:
        files = sorted(WEB.glob("*.md"))
    except OSError:
        return docs
    for f in files:
        try:
            size = f.stat().st_size
        except OSError:
            size = 0
        docs.append({
            "name": f.name,
            "size": size,
            "size_label": _human_size(size),
            "public": f.name in PUBLIC_DOCS,
        })
    return docs


def build_failed_marker() -> str | None:
    marker = WEB / ".last_build_failed"
    try:
        if marker.exists():
            return "ai build failed last " + marker.read_text().strip()
    except OSError:
        return "ai build failed last <unknown>"
    return None


WORKER_LOG = pathlib.Path("/var/log/opencode-worker.log")


def worker_run_summary() -> list[dict[str, str]]:
    """Parse per-run lines out of the worker log into a reverse-chron summary."""
    try:
        lines = WORKER_LOG.read_text(errors="replace").splitlines()
    except OSError:
        return []
    runs: dict[int, dict[str, str]] = {}
    order: list[int] = []
    for ln in lines:
        marker = " worker: run "
        if marker not in ln:
            continue
        try:
            pre, rest = ln.split(marker, 1)
            num, _, tail = rest.partition(" ")
            n = int(num)
            ts = pre.strip()
        except (ValueError, IndexError):
            continue
        if n not in runs:
            runs[n] = {"run": num, "ts": ts, "start": tail, "end": "", "rc": "", "status": ""}
            order.append(n)
        d = runs[n]
        if tail.startswith("start"):
            d["start"] = tail[len("start"):].strip().strip("()")
            d["ts"] = ts
        elif tail.startswith("done"):
            d["end"] = ts
            d["status"] = tail[len("done"):].strip()
        elif tail.startswith("committed"):
            d["status"] = d["status"] or "committed"
        elif tail.startswith("SITE DOWN"):
            d["status"] = "SITE DOWN (rolled back)"
        elif tail.startswith("finished"):
            d["status"] = d["status"] or "finished"
    return [runs[n] for n in reversed(order)]


def system_uptime() -> str:
    """Human uptime + boot time from /proc/uptime. '' if unavailable."""
    try:
        secs = float(pathlib.Path("/proc/uptime").read_text().split()[0])
        h, rem = divmod(int(secs), 3600)
        m = rem // 60
        boot = datetime.fromtimestamp(
            time.time() - secs, tz=timezone.utc
        ).strftime("%Y-%m-%d %H:%M UTC")
        return f"{h}h {m}m (boot {boot})"
    except Exception:  # noqa: BLE001
        return ""


def chat_scroll_js() -> str:
    """Scroll `#chat-log` so the newest message is fully visible top-to-bottom.

    If the message is taller than the viewport (can't fit), its top is aligned
    with the top of the chat container instead. Wrapped in an IIFE because
    Reflex evaluates `call_script` bodies with eval() — top-level `return`
    would be an "Illegal return statement".
    """
    return (
        "(function(){"
        "var log=document.getElementById('chat-log');"
        "if(!log)return;"
        "var kids=[].filter.call(log.children,function(c){return c.nodeType===1;}),"
        "last=kids.length?kids[kids.length-1]:null;"
        "if(!last){log.scrollTop=log.scrollHeight;return;}"
        "var ch=log.clientHeight,mh=last.offsetHeight,top=last.offsetTop;"
        "if(mh>=ch){log.scrollTop=top;return;}"
        "var want=top+mh-ch;"
        "if(want>log.scrollTop)log.scrollTop=want;"
        "})()"
    )


def chat_ding_js() -> str:
    """Smart-scroll the visitor chat and play the soft message-end ding."""
    return chat_scroll_js() + ";if(window.playDing)playDing();"


def live_chat_scroll_js() -> str:
    """Scroll the admin's `#live-chat-log` box to the newest message."""
    return (
        "var el=document.getElementById('live-chat-log');"
        "if(el)el.scrollTop=el.scrollHeight;"
    )


def _focus_js(element_id: str) -> str:
    """Restore keyboard focus to an input after the UI re-renders."""
    return (
        "(function(){"
        "var el=document.getElementById('" + element_id + "');"
        "if(!el)return;"
        "el.focus();"
        "var t=el.value.length;"
        "try{el.setSelectionRange(t,t);}catch(e){}"
        "})()"
    )


def setup_avatar_editor_js() -> str:
    """Attach pan/zoom handlers to the circular avatar crop viewport.

    The image is a box of `2*S*z` px (S=220, z=1..4) centred inside the 220px
    circle; the visitor pans and zooms to frame their face. Pan/zoom state is
    kept on the element (``__avoff``/``__z``) so the Save button crops from the
    exact same geometry. Oversized sources are downscaled in place to keep the
    canvas crop memory-bounded.
    """
    return (
        "(function(){"
        "var v=document.getElementById('avatar-crop-view');"
        "if(!v||v.__avready)return;"
        "v.__avready=true;"
        "var img=document.getElementById('avatar-crop-img');"
        "var S=220,z=1,dx=0,dy=0,ox=0,oy=0,sx=0,sy=0,on=false;"
        "v.__avoff={dx:0,dy:0};v.__z=1;"
        "v.__mime=(img&&img.src)||'';"
        "function apply(){"
        "  var R=S*(z-0.5);"
        "  dx=Math.max(-R,Math.min(R,dx));"
        "  dy=Math.max(-R,Math.min(R,dy));"
        "  v.__avoff={dx:dx,dy:dy};v.__z=z;"
        "  if(img){"
        "    img.style.width=(S*2*z)+'px';"
        "    img.style.height=(S*2*z)+'px';"
        "    img.style.transform='translate(-50%,-50%) translate('+dx+'px,'+dy+'px)';"
        "  }"
        "}"
        "function setZoom(nz){"
        "  z=Math.max(1,Math.min(4,nz));apply();"
        "}"
        "v.__zoom=setZoom;"
        "v.addEventListener('pointerdown',function(e){"
        "  on=true;sx=e.clientX;sy=e.clientY;ox=dx;oy=dy;"
        "  try{v.setPointerCapture(e.pointerId);}catch(err){}"
        "});"
        "v.addEventListener('pointermove',function(e){"
        "  if(!on)return;"
        "  dx=ox+(e.clientX-sx);dy=oy+(e.clientY-sy);"
        "  apply();"
        "});"
        "function up(){on=false;}"
        "v.addEventListener('pointerup',up);"
        "v.addEventListener('pointercancel',up);"
        "v.addEventListener('wheel',function(e){"
        "  e.preventDefault();"
        "  setZoom(z+(e.deltaY<0?0.1:-0.1));"
        "},{passive:false});"
        "apply();"
        "function downscale(){"
        "  var nw=img.naturalWidth||0,nh=img.naturalHeight||0,MAX=2048;"
        "  if(!nw||!nh||Math.max(nw,nh)<=MAX)return;"
        "  var k=MAX/Math.max(nw,nh);"
        "  var c=document.createElement('canvas');"
        "  c.width=Math.round(nw*k);c.height=Math.round(nh*k);"
        "  var ctx=c.getContext('2d');"
        "  if(!ctx)return;"
        "  ctx.drawImage(img,0,0,c.width,c.height);"
        "  img.src=c.toDataURL('image/jpeg',0.88);"
        "}"
        "if(img&&!img.complete){img.addEventListener('load',downscale);}"
        "else if(img){downscale();}"
        "})()"
    )


def zoom_avatar_js(dz: float) -> str:
    """Step the avatar editor zoom by dz via the stored `__zoom` closure."""
    return (
        "(function(){"
        "var v=document.getElementById('avatar-crop-view');"
        "if(!v||!v.__zoom)return;"
        "v.__zoom(" + repr(float(dz)) + ");"
        "})()"
    )


def crop_avatar_js() -> str:
    """Canvas-crop the visible square of the avatar editor; returns a data URI.

    Mirrors the CSS geometry: the view is S=220px, the image box is 2*S*z px
    centred with translate(-50%,-50%) then panned by the stored offset. The
    drawn region [0,S]x[0,S] is exactly what the circular frame shows. PNG is
    exported for transparent sources (png/webp) so corners never turn black.
    """
    return (
        "(function(){"
        "var v=document.getElementById('avatar-crop-view');"
        "if(!v)return '';"
        "var img=document.getElementById('avatar-crop-img');"
        "if(!img)return '';"
        "var S=220;"
        "var nw=img.naturalWidth||0,nh=img.naturalHeight||0;"
        "if(!nw||!nh)return '';"
        "var z=v.__z||1,off=v.__avoff||{dx:0,dy:0};"
        "var scale=Math.max(S*2*z/nw,S*2*z/nh);"
        "var dw=nw*scale,dh=nh*scale;"
        "var boxL=S*(0.5-z)+off.dx,boxT=S*(0.5-z)+off.dy;"
        "var iL=boxL+(S*2*z-dw)/2,iT=boxT+(S*2*z-dh)/2;"
        "var c=document.createElement('canvas');"
        "c.width=S;c.height=S;"
        "var ctx=c.getContext('2d');"
        "if(!ctx)return '';"
        "ctx.imageSmoothingEnabled=true;ctx.imageSmoothingQuality='high';"
        "ctx.drawImage(img,iL,iT,dw,dh);"
        "var mime=(v.__mime||'').toLowerCase();"
        "var png=mime.indexOf('image/png')===0||mime.indexOf('image/webp')===0;"
        "return c.toDataURL(png?'image/png':'image/jpeg',0.92);"
        "})()"
    )


def _visitor_notify_text(ctx: dict[str, str], ip: str, geo: dict[str, str]) -> str:
    """Full visitor fingerprint for the owner's ntfy notification (incl. IP)."""
    ctx = ctx or {}
    geo = geo or {}
    latlon = ""
    if geo.get("lat") and geo.get("lon"):
        latlon = f"{geo['lat']},{geo['lon']}"
    fields = [
        ("IP", ip),
        ("Location", ctx.get("location")),
        ("Country", geo.get("country")),
        ("Country code", geo.get("country_code")),
        ("Region", geo.get("region")),
        ("City", geo.get("city")),
        ("Lat/Lon", latlon),
        ("Timezone", geo.get("timezone") or ctx.get("tz")),
        ("Language", ctx.get("lang")),
        ("Locale", ctx.get("locale")),
        ("Platform", ctx.get("platform")),
        ("Device", ctx.get("device")),
        ("Local time", ctx.get("local_time")),
        ("Time of day", ctx.get("time_of_day")),
        ("Weather", ctx.get("weather")),
        ("Temp", ctx.get("temp")),
        ("Feels like", ctx.get("feels_like")),
        ("Humidity", ctx.get("humidity")),
        ("Pressure", ctx.get("pressure")),
        ("Wind", ctx.get("wind")),
        ("Precip", ctx.get("precip")),
        ("Warning", ctx.get("warning")),
        ("Sunrise", ctx.get("sunrise")),
        ("Sunset", ctx.get("sunset")),
        ("Moon", ctx.get("moon")),
    ]
    return "\n".join(f"{k}: {v}" for k, v in fields if v)


def _visitor_context_text(ctx: dict[str, str], user_email: str = "", user_name: str = "", is_admin: bool = False) -> str:
    """Format the collected visitor context into an LLM-readable block."""
    lines = [
        "\n\nVISITOR CONTEXT (everything known about the current visitor; use it to "
        "personalise answers):"
    ]
    if user_email:
        if is_admin:
            lines.append(f"- Identified as: SITE OWNER / ADMIN ({user_name or 'Frank'}, {user_email}).")
            lines.append(
                "- This is Frank, who runs this site. Address them as the person in charge. "
                "They are fully trusted and may discuss internal site operations, the stack, "
                "deployment, code, and admin dashboards openly. Do not ask them who they are."
            )
        else:
            lines.append(f"- Identified Email: {user_email}")
            if user_name:
                lines.append(f"- User Name: {user_name}")
            lines.append("- They have an account or have identified themselves.")
    else:
        lines.append("- Unidentified Guest (No email provided).")
        lines.append("- You can ask for their email to remember them, and suggest setting a password for safe chat history.")

    if not ctx:
        return "\n".join(lines)

    if ctx.get("lang"):
        lines.append(f"- language: {ctx['lang']}")
    if ctx.get("locale"):
        lines.append(f"- locale: {ctx['locale']}")
    if ctx.get("platform"):
        lines.append(f"- platform: {ctx['platform']}")
    if ctx.get("is_windows"):
        lines.append("- Windows: flag emoji must NOT be used (fonts can't render them)")
    if ctx.get("local_time"):
        lines.append(f"- local time: {ctx['local_time']} ({ctx.get('time_of_day', '')})")
    if ctx.get("location"):
        lines.append(f"- location: {ctx['location']}")
    if ctx.get("weather"):
        parts = [f"- weather: {ctx['weather']}"]
        if ctx.get("temp"):
            parts.append(f"temp {ctx['temp']}")
        if ctx.get("feels_like"):
            parts.append(f"feels like {ctx['feels_like']}")
        if ctx.get("humidity"):
            parts.append(f"humidity {ctx['humidity']}")
        if ctx.get("pressure"):
            parts.append(f"pressure {ctx['pressure']}")
        if ctx.get("wind"):
            parts.append(f"wind {ctx['wind']}")
        if ctx.get("precip"):
            parts.append(f"precipitation {ctx['precip']}")
        lines.append(" ".join(parts))
    if ctx.get("sunrise") or ctx.get("sunset"):
        lines.append(f"- sun: rise {ctx.get('sunrise', '?')} / set {ctx.get('sunset', '?')} local")
    if ctx.get("moon"):
        lines.append(f"- moon: {ctx['moon']} {ctx.get('moon_emoji', '')}")
    if ctx.get("warning"):
        lines.append(f"- weather warning: {ctx['warning']}")
    if ctx.get("device"):
        lines.append(f"- device: {ctx['device']}")
    return "\n".join(lines)


def _system_message(ctx: dict[str, str] | None = None, user_email: str = "", user_name: str = "", is_admin: bool = False) -> dict[str, str]:
    return {
        "role": "system",
        "content": (
            read_doc("prompt.md")
            + "\n\nKNOWLEDGE:\n"
            + read_doc("knowledge.md")
            + _visitor_context_text(ctx or {}, user_email, user_name, is_admin)
        ),
    }


async def _ai_call(messages: list[dict[str, str]]) -> str:
    """Full (non-streamed) completion via the remote Ollama endpoint."""
    client = get_chat_client()
    if client is None:
        return FALLBACK
    resp = await client.chat.completions.create(
        model=CHAT_MODEL,
        messages=messages,
        temperature=0.4,
        reasoning_effort="none",
        max_tokens=2048,
    )
    return resp.choices[0].message.content.strip()


def _estimate_tokens(msgs: list[dict]) -> int:
    """Rough token estimate (≈4 chars/token) for the compactor threshold."""
    return sum(max(1, len((m.get("content") or "")) // 4) for m in msgs)


async def _compact_conversation(conv_id: str) -> bool:
    """Self-assigned compaction: summarise an over-long thread into history.

    If a conversation's transcript is estimated past `COMPACT_TOKEN_THRESHOLD`
    tokens, ask the LLM to write a faithful summary; that summary then replaces
    the thread (archived to a capped sidecar for audit). Returns True when the
    thread was compacted.
    """
    msgs = site_store.get_conv_messages(conv_id)
    if not msgs or _estimate_tokens(msgs) <= COMPACT_TOKEN_THRESHOLD:
        return False
    logger.info("compactor: conv %s over threshold (%d msgs, ~%d tokens) -> summarizing",
                conv_id, len(msgs), _estimate_tokens(msgs))
    transcript = "\n\n".join(
        f"{m.get('role', '?').upper()}: {m.get('content', '')}" for m in msgs
    )
    system = (
        "You are a conversation compactor. Summarise the chat below into one "
        "faithful, dense history that preserves: who the visitor is (name, email, "
        "location, anything personal they shared), every topic discussed, all "
        "commitments/decisions, and the tone of the conversation. Keep the last "
        "3 exchanges verbatim at the very end. Write in the same language the "
        "visitor used. Output ONLY the summary as plain text - no preamble, no "
        "headings like 'Summary:', no markdown."
    )
    try:
        summary = await _ai_call([
            {"role": "system", "content": system},
            {"role": "user", "content": transcript},
        ])
    except Exception:  # noqa: BLE001
        logger.exception("compactor: summarisation failed for %s", conv_id)
        return False
    summary = summary.strip()
    if not summary:
        return False
    stamped = time.time()
    new_history = [{
        "role": "system",
        "content": "Previous conversation summary:\n" + summary,
        "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "compacted": True,
        "compacted_from": len(msgs),
    }]
    site_store.archive_compact(conv_id, msgs)
    ok = site_store.set_conv_messages(
        conv_id, new_history,
        extra={"compacted": True, "compacted_at": stamped, "last_activity_epoch": stamped},
    )
    logger.info("compactor: compacted %s -> summary (%d msgs archived)", conv_id, len(msgs))
    return ok


async def filter_draft(question: str, draft: str) -> tuple[bool, str]:
    system = (
        "You are a strict quality filter. Apply the requirements below to the "
        'draft answer and reply with JSON only: {"pass": true} or '
        '{"pass": false, "reason": "..."}.\n\nREQUIREMENTS:\n'
        + read_doc("filter.md")
    )
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": f"Visitor question: {question}\n\nDraft answer to review:\n\n{draft}"},
    ]
    try:
        raw = await _ai_call(messages)
        start = raw.find("{")
        data = json.loads(raw[start : raw.find("}", start) + 1])
        return bool(data.get("pass")), str(data.get("reason", ""))
    except Exception as exc:  # noqa: BLE001
        logger.warning("filter parse failed (%s), passing draft", exc)
        return True, ""


class State(rx.State):
    messages: list[dict[str, str]] = []
    busy: bool = False
    greeted: bool = False
    # True while the personal greeting is streaming into `messages`, so the
    # visitor-chat store mirror never wipes the half-built bubble.
    greeting_in_progress: bool = False
    visitor_context: dict[str, str] = {}
    suggestions: list[str] = []
    has_unread: bool = False

    def clear_unread(self):
        self.has_unread = False
        self._last_admin_msg_count = site_store.message_count()

    def open_chat_popup(self):
        self.chat_popup_open = True

    def close_chat_popup(self):
        self.chat_popup_open = False

    @rx.var
    def notifications_enabled(self) -> bool:
        import notify
        return notify.get_notifications_state()

    def toggle_admin_notifications(self, state: bool):
        import notify
        notify.toggle_notifications(state)

    # Auth session: the cookie holds an opaque token; identity is re-verified
    # against site_store.sessions.json on every page load, never trusted from
    # the client alone.
    session_token: str = rx.Cookie("", name="cv_sess", max_age=30 * 86400, same_site="lax", secure=False)
    user_email: str = ""
    user_name: str = ""
    user_role: str = ""
    is_admin: bool = False
    auth_error: str = ""

    # Per-session analytics/transcript identifiers.
    conv_id: str = ""
    visitor_ip: str = ""
    visitor_id: str = ""  # stable localStorage id, groups convs per browser/user

    # Profile Picture & Editing
    user_avatar: str = ""
    avatar_pending: str = ""   # raw uploaded image shown in the crop editor
    is_editing_avatar: bool = False
    avatar_saved: bool = False # flash "Saved ✓" after the crop is persisted
    avatar_error: str = ""     # upload rejection reason (e.g. file too large)
    is_editing_profile: bool = False

    # Floating chat window
    chat_popup_open: bool = False                     # True: FAB opens the popup

    async def handle_avatar_upload(self, files: list[rx.UploadFile]):
        if not files or not self.user_email:
            return
        upload_data = await files[0].read()
        if len(upload_data) > 15 * 1024 * 1024:
            self.avatar_pending = ""
            self.is_editing_avatar = False
            self.avatar_saved = False
            self.avatar_error = "Image is too large (max 15 MB)."
            return
        import base64
        b64 = base64.b64encode(upload_data).decode("utf-8")
        mime_type = files[0].content_type or "image/png"
        # Stage the raw image for the crop editor; nothing is persisted until
        # the visitor presses Save (which uploads the panned crop).
        self.avatar_pending = f"data:{mime_type};base64,{b64}"
        self.is_editing_avatar = True
        self.avatar_saved = False
        self.avatar_error = ""
        return rx.call_script(setup_avatar_editor_js())

    def save_avatar_cropped(self, data_uri: str):
        """Persist the cropped avatar produced by the client-side canvas crop."""
        if not self.user_email or not data_uri or not self.is_editing_avatar:
            return
        self.user_avatar = data_uri
        self.avatar_pending = ""
        self.is_editing_avatar = False
        self.avatar_error = ""
        self.avatar_saved = True
        site_store.update_user_profile(self.user_email, {"avatar": data_uri})

    def cancel_avatar_edit(self):
        self.avatar_pending = ""
        self.is_editing_avatar = False
        self.avatar_saved = False
        self.avatar_error = ""

    def save_profile_name(self, form_data: dict):
        if not self.user_email:
            return
        new_name = form_data.get("name", self.user_name)
        self.user_name = new_name
        site_store.update_user_profile(self.user_email, {"name": new_name})
        self.is_editing_profile = False

    def toggle_edit_profile(self):
        self.is_editing_profile = not self.is_editing_profile

    visitor_geo: dict[str, str] = {}

    # Admin dashboard payload (populated only by load_admin after token check).
    admin_stats: dict[str, int] = {}
    admin_locations: list[dict[str, object]] = []
    admin_pages: list[dict[str, object]] = []
    admin_visits: list[dict[str, object]] = []
    admin_log: str = ""
    _last_admin_msg_count: int = -1

    # Threads + users lists (one card per conversation / person), paginated.
    admin_threads: list[dict[str, str]] = []
    admin_threads_page: list[dict[str, str]] = []
    admin_thread_page: int = 0
    admin_users: list[dict[str, str]] = []
    admin_users_page: list[dict[str, str]] = []
    admin_user_page: int = 0

    @rx.var
    def admin_thread_pages(self) -> int:
        return max(1, (len(self.admin_threads) + ADMIN_PAGE_SIZE - 1) // ADMIN_PAGE_SIZE)

    @rx.var
    def admin_user_pages(self) -> int:
        return max(1, (len(self.admin_users) + ADMIN_PAGE_SIZE - 1) // ADMIN_PAGE_SIZE)

    def _slice_page(self, full: list, page: int) -> list:
        start = page * ADMIN_PAGE_SIZE
        return full[start : start + ADMIN_PAGE_SIZE]

    def _repage(self) -> None:
        """Clamp current pages and refresh the displayed slices."""
        self.admin_thread_page = max(0, min(
            self.admin_thread_page,
            (len(self.admin_threads) - 1) // ADMIN_PAGE_SIZE,
        ))
        self.admin_user_page = max(0, min(
            self.admin_user_page,
            (len(self.admin_users) - 1) // ADMIN_PAGE_SIZE,
        ))
        self.admin_threads_page = self._slice_page(self.admin_threads, self.admin_thread_page)
        self.admin_users_page = self._slice_page(self.admin_users, self.admin_user_page)

    def admin_threads_prev(self):
        if self.admin_thread_page > 0:
            self.admin_thread_page -= 1
            self.admin_threads_page = self._slice_page(self.admin_threads, self.admin_thread_page)

    def admin_threads_next(self):
        if self.admin_thread_page + 1 < self.admin_thread_pages:
            self.admin_thread_page += 1
            self.admin_threads_page = self._slice_page(self.admin_threads, self.admin_thread_page)

    def admin_users_prev(self):
        if self.admin_user_page > 0:
            self.admin_user_page -= 1
            self.admin_users_page = self._slice_page(self.admin_users, self.admin_user_page)

    def admin_users_next(self):
        if self.admin_user_page + 1 < self.admin_user_pages:
            self.admin_user_page += 1
            self.admin_users_page = self._slice_page(self.admin_users, self.admin_user_page)

    # Content editor (admin-only): the doc being edited + live preview source.
    page_doc: str = ""          # which <doc>.md is loaded on a public page
    page_body: str = ""         # rendered body of the current page (from read_doc)
    home_title: str = _DEFAULT_HOME_TITLE  # main-page H1 (home.md)
    home_intro: str = _DEFAULT_HOME_INTRO  # rendered main-page intro (home.md)
    doc_edit_source: str = ""   # working textarea buffer in the admin editor
    editing_doc: str = ""       # <doc>.md currently open in the admin editor
    doc_saved: bool = False     # flash "Saved" after a successful write
    admin_docs: list[dict[str, object]] = []  # file-manager list for the Pages tab

    async def load_public_doc(self, doc_name: str):
        """on_load for content pages: restore session, log the visit, read the doc."""
        self._restore_session()
        await self._record_visit()
        self.page_doc = doc_name
        self.page_body = read_doc(doc_name)
        self.editing_doc = doc_name

    def open_doc_editor(self, doc_name: str):
        """Open a markdown doc in the admin WYSIWYG editor (loads current source)."""
        self.editing_doc = doc_name
        self.doc_edit_source = read_doc(doc_name)
        self.doc_saved = False

    def close_doc_editor(self):
        """Return from the editor to the Pages file-manager list."""
        self.editing_doc = ""
        self.doc_edit_source = ""
        self.doc_saved = False

    def set_doc_edit_source(self, value: str):
        self.doc_edit_source = value or ""

    def save_doc(self):
        """Write the admin editor buffer back to /web/<doc>.md (crash-safe)."""
        name = self.editing_doc
        if not name or not name.endswith(".md") or "/" in name:
            return
        source = self.doc_edit_source
        if not isinstance(source, str):
            return
        try:
            tmp = WEB / f".{name}.tmp"
            tmp.write_text(source)
            os.replace(tmp, WEB / name)
        except OSError:
            logger.exception("doc save failed: %s", name)
            return
        self.page_body = source
        if name == "home.md":
            self.home_title, self.home_intro = parse_home_doc(source)
        self.doc_saved = True

    # Live Chat State
    live_chat_input: str = ""
    active_live_chat_id: str = ""
    live_chat_messages: list[dict[str, str]] = []
    edit_msg_idx: int = -1
    edit_msg_text: str = ""

    def set_active_live_chat(self, conv_id: str):
        self.active_live_chat_id = conv_id
        self.edit_msg_idx = -1
        site_store.toggle_ai_pause(conv_id, True)
        self.refresh_live_chat()

    def refresh_live_chat(self):
        if not self.active_live_chat_id:
            return
        convs = site_store._read("conversations.json", [])
        for c in convs:
            if c.get("id") == self.active_live_chat_id:
                self.live_chat_messages = [
                    {
                        **m,
                        "idx": i,
                        "edited": "edited" if m.get("edited") else "",
                        "compacted": "compacted summary" if m.get("compacted") else "",
                    }
                    for i, m in enumerate(c.get("messages", []))
                ]
                return rx.call_script(live_chat_scroll_js())

    # --- Visitor-side store mirror (unifies the home chat with the takeover) ---

    def _register_visitor(self) -> None:
        """Register this session's socket token for instant chat push."""
        try:
            token = self.router.session.client_token or ""
        except Exception:  # noqa: BLE001
            token = ""
        if self.conv_id and token:
            _register_visitor_token(self.conv_id, token)

    def _sync_visitor_transcript(self) -> bool:
        """Mirror the store transcript for this visitor into `messages`.

        Identified, non-guest users skip the leading greeting (same slice the
        session already shows); guests get the full transcript. Never runs while
        an AI stream or the greeting is in flight, and only assigns when the
        transcript actually changed (so an unchanged poll emits no delta).
        """
        if self.busy or self.greeting_in_progress:
            return False
        if not self.conv_id:
            return False
        self._register_visitor()
        convs = site_store.get_full_conversations()
        conv = next((c for c in convs if c.get("id") == self.conv_id), None)
        if conv is None:
            return False
        transcript = conv.get("messages", [])
        user = site_store.get_user(self.user_email)
        is_guest = user.get("guest", False) if user else True
        # Non-guests drop the leading greeting bubble, but NEVER a compacted
        # summary (that IS the history and must stay visible).
        if not is_guest and len(transcript) > 1 and not transcript[0].get("compacted"):
            transcript = transcript[1:]
        if transcript == self.messages:
            return False
        self.messages = transcript
        return True

    def refresh_visitor_chat(self):
        """Auto-refresh tick for `/`: mirror the store into the visitor chat.

        Re-arms itself until the visitor leaves the home page.
        """
        page_path = getattr(getattr(self.router, "url", None), "path", "") or ""
        if page_path not in ("", "/", "/index"):
            return
        changed = self._sync_visitor_transcript()
        rearm = rx.call_script(
            auto_refresh_js(VISITOR_CHAT_POLL_MS), callback=State.refresh_visitor_chat
        )
        if changed:
            return [rx.call_script(chat_ding_js()), rearm]
        return rearm

    def visitor_chat_refreshed(self):
        """Push target: an admin edit/takeover reply just landed on this thread."""
        if self._sync_visitor_transcript():
            return rx.call_script(chat_ding_js())

    async def _push_to_visitors(self, conv_id: str) -> None:
        """Best-effort instant push to every live visitor on a conversation.

        Enqueues a refresh event on the visitor's socket so their transcript
        updates immediately; the visitor-side poll remains the fallback.
        """
        if not conv_id:
            return
        for token in list((_CONV_TOKENS.get(conv_id) or {}).keys()):
            try:
                await app.event_processor.enqueue(
                    token,
                    Event(
                        name="reflex___state____state.main____state.visitor_chat_refreshed",
                        payload={},
                        router_data={},
                    ),
                )
            except Exception:  # noqa: BLE001
                logger.exception("chat push to visitor %s failed", token[:10])

    def start_edit_msg(self, idx: str):
        idx = int(idx)
        for m in self.live_chat_messages:
            if int(m["idx"]) == idx:
                self.edit_msg_idx = idx
                self.edit_msg_text = m["content"]
                break

    def cancel_edit_msg(self):
        self.edit_msg_idx = -1
        self.edit_msg_text = ""

    def set_edit_msg_text(self, value: str):
        self.edit_msg_text = value or ""

    async def save_edit_msg(self):
        if self.edit_msg_idx < 0 or not self.edit_msg_text.strip() or not self.active_live_chat_id:
            return
        if site_store.edit_conv_message(self.active_live_chat_id, self.edit_msg_idx, self.edit_msg_text.strip()):
            self.edit_msg_idx = -1
            self.edit_msg_text = ""
            self.refresh_live_chat()
            await self._push_to_visitors(self.active_live_chat_id)

    async def send_live_chat_message(self, form_data: dict):
        msg = form_data.get("message", "").strip()
        if not msg or not self.active_live_chat_id:
            return
        # Takeover reply goes into the VISITOR's thread: do NOT stamp it with
        # the admin's email, or it gets hijacked into the admin's own history.
        site_store.log_conv_message(self.active_live_chat_id, "assistant", msg)
        self.live_chat_input = ""
        self.refresh_live_chat()
        await self._push_to_visitors(self.active_live_chat_id)

    def resume_ai_chat(self):
        if self.active_live_chat_id:
            site_store.toggle_ai_pause(self.active_live_chat_id, False)
            self.active_live_chat_id = ""


    @rx.var
    def is_logged_in(self) -> bool:
        return bool(self.user_email)

    @rx.var
    def show_suggestions(self) -> bool:
        """Show example chips until the visitor sends their first question.

        The greeting is an assistant message, so it must not count — only a
        user message hides the chips.
        """
        return not any(m.get("role") == "user" for m in self.messages)

    def _restore_session(self) -> None:
        """Re-derive identity from the cookie token (runs on every page load)."""
        token = self.session_token or ""
        sess = site_store.validate_session(token)
        if sess is None:
            if token:
                self.session_token = ""
            self.user_email = ""
            self.user_name = ""
            self.user_role = ""
            self.is_admin = False
            return
        self.user_email = sess["email"]
        self.user_name = sess.get("name", "") or sess["email"].split("@")[0]
        self.user_role = sess["role"]
        self.is_admin = sess["role"] == "admin"

        # Load user to check if guest
        user = site_store.get_user(self.user_email)
        is_guest = user.get("guest", False) if user else True

        # If they are not a guest and have no messages currently loaded (or maybe just on load),
        # we can restore their latest conversation history
        if not is_guest and not self.messages:
            convs = site_store.get_user_conversations(self.user_email)
            if convs:
                latest_conv = convs[0]
                msgs = latest_conv.get("messages", [])
                if len(msgs) > 1 and not msgs[0].get("compacted"):
                    msgs = msgs[1:]
                if msgs:
                    self.messages = msgs
                    self.conv_id = latest_conv["id"]

    async def _record_visit(self) -> None:
        """Log a page view into the analytics store (skips the admin's own views).

        Never blocks page load on a geo lookup: writes immediately with any
        cached geo and lets a background task enrich + backfill the row.
        """
        try:
            if self.user_role == "admin":
                return
            router = self.router
            headers = router.headers
            raw = getattr(headers, "raw_headers", None) or {}
            ip = _real_client_ip(router)
            path = getattr(router.url, "path", None) or "/"
            if path in ("", "/index"):
                path = "/"
            ua = raw.get("user-agent") or raw.get("User-Agent") or ""
            ref = raw.get("referer") or raw.get("Referer") or ""
            lang = headers.accept_language or ""
            geo: dict[str, str] = {}
            with _GEO_LOCK:
                cached = _GEO_CACHE.get(ip)
                if cached:
                    geo = dict(cached)
            site_store.log_visit(path=path, ip=ip, geo=geo, lang=lang, ua=ua, ref=ref)
            if cached is None and ip:
                asyncio.get_running_loop().create_task(_enrich_visit(ip))
        except Exception:  # noqa: BLE001
            logger.exception("visit recording failed")

    async def load_home(self):
        """on_load for `/`: restore session, log the visit, probe the browser."""
        self._restore_session()
        await self._record_visit()
        self.suggestions = random.sample(SUGGESTIONS, 2)
        self.home_title, self.home_intro = parse_home_doc(read_doc("home.md"))
        return [
            rx.call_script(BROWSER_INFO_JS, callback=State.on_browser_info),
            rx.call_script(
                auto_refresh_js(VISITOR_CHAT_POLL_MS),
                callback=State.refresh_visitor_chat,
            ),
        ]

    async def load_public(self) -> None:
        """on_load for public content pages: restore session + log the visit."""
        self._restore_session()
        await self._record_visit()

    def load_profile(self) -> None:
        self._restore_session()

    async def load_admin(self):
        """on_load for `/admin`: guard, then pull the analytics payload."""
        self._restore_session()
        if not self.is_admin:
            return rx.redirect("/")
        self._load_admin_payload()
        # Kick off the auto-refresh loop. Each tick re-arms itself via the
        # call_script callback; it stops once the admin leaves the page.
        return rx.call_script(auto_refresh_js(ADMIN_POLL_MS), callback=State.refresh_admin)

    def _load_admin_payload(self) -> None:
        """Read the whole dashboard payload into state (shared by load + poll)."""
        data = site_store.admin_data()
        self.admin_stats = {
            "total": data["total"],
            "unique": data["unique"],
            "convs": data["convs"],
            "messages": data["messages"],
        }
        self.admin_locations = data["locations"]
        self.admin_pages = data["pages"]
        self.admin_visits = data["recent"]
        self.admin_threads = data["threads"]
        self.admin_users = data["users"]
        self.admin_docs = list_editable_docs()
        self._repage()
        self.admin_log = server_log_tail(40)
        if self.active_live_chat_id:
            self.refresh_live_chat()

    def refresh_admin(self):
        """Auto-refresh tick for /admin. Guards, reloads, re-arms the poll.

        Silently returns (loop stops) once the admin navigates away or loses
        their session, so a stale timer can't keep polling in the background.
        """
        self._restore_session()
        if not self.is_admin:
            return
        page_path = getattr(getattr(self.router, "url", None), "path", "") or ""
        if not page_path.startswith("/admin"):
            return
        # New visitor/user messages while not actively chatting -> ring the bell.
        if not self.active_live_chat_id and not self.busy:
            now_count = site_store.message_count()
            if self._last_admin_msg_count >= 0 and now_count > self._last_admin_msg_count:
                self.has_unread = True
            self._last_admin_msg_count = now_count
        self._load_admin_payload()
        ms = LIVE_CHAT_POLL_MS if self.active_live_chat_id else ADMIN_POLL_MS
        return rx.call_script(auto_refresh_js(ms), callback=State.refresh_admin)

    async def do_login(self, form_data: dict):
        email = str(form_data.get("email") or "").strip().lower()
        password = str(form_data.get("password") or "")

        ok, msg, user = site_store.authenticate(email, password)
        if not ok:
            self.auth_error = msg
            return

        is_guest = user.get("guest", False)
        self.auth_error = ""
        self.user_email = email
        self.user_name = user.get("name", "") or email.split("@")[0]
        self.user_role = user["role"]
        self.is_admin = user["role"] == "admin"
        self.session_token = site_store.create_session(email, user["role"], self.user_name)

        if not is_guest:
            # Verified user with password: load their history
            convs = site_store.get_user_conversations(email)
            if convs:
                latest_conv = convs[0]
                msgs = latest_conv.get("messages", [])
                if len(msgs) > 1 and not msgs[0].get("compacted"):
                    msgs = msgs[1:]
                if msgs:
                    self.messages = msgs
                    self.conv_id = latest_conv["id"]

        if self.is_admin:
            _notify("Admin login", f"{email} signed in to the admin dashboard.", ["lock"])

        return rx.redirect("/")

    async def do_signup(self, form_data: dict):
        name = str(form_data.get("name") or "").strip()
        email = str(form_data.get("email") or "").strip().lower()
        password = str(form_data.get("password") or "")
        confirm = str(form_data.get("confirm") or "")
        if password != confirm:
            self.auth_error = "Passwords do not match."
            return
        ok, msg = site_store.create_user(name, email, password)
        if not ok:
            self.auth_error = msg
            return
        self.auth_error = ""
        self.user_email = email
        self.user_name = name or email.split("@")[0]
        self.user_role = "user"
        self.is_admin = False
        self.session_token = site_store.create_session(email, "user", self.user_name)
        _notify("New signup", f"{self.user_name} <{email}> subscribed for updates.", ["party_popper"])
        return rx.redirect("/")

    async def do_signout(self):
        if self.session_token:
            site_store.destroy_session(self.session_token)
        self.session_token = ""
        self.user_email = ""
        self.user_name = ""
        self.user_role = ""
        self.is_admin = False
        return rx.redirect("/")

    async def on_browser_info(self, info: str):
        """First event: browser fingerprint from the client -> personal greeting.

        Runs on page load (via on_load -> rx.call_script callback). Guarded by
        `greeted` so navigating back to `/` doesn't greet twice per session.
        """
        if self.greeted:
            return
        self.greeted = True
        self.greeting_in_progress = True
        logger.info("greeting: on_browser_info raw=%r", info)

        browser: dict[str, str] = {}
        try:
            browser = json.loads(info or "{}")
            # Reflex may deliver the JS result double-JSON-encoded (a quoted
            # string). Unwrap one layer so `browser` is a dict, not a string.
            if isinstance(browser, str):
                logger.info("greeting: info was double-encoded, unwrapping")
                browser = json.loads(browser)
            if not isinstance(browser, dict):
                logger.info("greeting: info parsed to %r, resetting", type(browser).__name__)
                browser = {}
        except Exception:  # noqa: BLE001
            logger.warning("greeting: failed to parse info, treating as empty", exc_info=True)
        logger.info("greeting: browser=%r", browser)

        header = self.router.headers  # server-side, from the HTTP request
        ip = self.router.session.client_ip
        # Behind the Tailscale Funnel the real client IP usually comes through
        # x-forwarded-for (set by the funnel). Fall back to the socket IP.
        # raw_headers preserves the original (likely hyphenated) header keys.
        raw = getattr(header, "raw_headers", None) or {}
        forwarded = raw.get("x-forwarded-for") or raw.get("X-Forwarded-For") or ""
        real_ip = forwarded.partition(",")[0].strip() or ip
        logger.info("greeting: ip=%r forwarded=%r -> real_ip=%r", ip, forwarded, real_ip)
        geo = await _geo_for(real_ip)
        logger.info("greeting: geo=%r", geo)
        self.visitor_ip = real_ip
        self.visitor_geo = geo
        if not self.conv_id:
            self.conv_id = "c_" + secrets.token_hex(6)
        # Stable per-browser identity (localStorage), persisted client-side so
        # returning anonymous visitors keep the same thread grouping.
        self.visitor_id = browser.get("visitor") or self.visitor_id or ("v_" + secrets.token_hex(8))

        # Language: prefer the browser's reported language, then the header.
        prefs = (
            browser.get("lang")
            or browser.get("langs")
            or header.accept_language
            or ""
        )
        lang = detect_language(prefs) if prefs else "English"
        logger.info("greeting: lang=%r (prefs=%r, accept=%r)", lang, prefs, header.accept_language)

        # Visitor's local time: derive from the browser-reported epoch ms and
        # timezone so "good evening" matches where they actually are.
        local_epoch_s = 0
        try:
            local_epoch_s = float(browser.get("now") or 0) / 1000.0
        except (TypeError, ValueError):
            pass
        tz_name = browser.get("tz") or geo.get("timezone") or "UTC"
        local_hour: int | None = None
        try:
            local_hour = datetime.fromtimestamp(local_epoch_s, ZoneInfo(tz_name)).hour
        except Exception:  # noqa: BLE001
            local_hour = None
        logger.info("greeting: tz=%r local_hour=%r", tz_name, local_hour)
        time_of_day = _time_of_day(local_hour) if local_hour is not None else ""

        # --- Collect everything known about the visitor into one dict. ---
        # Stored on State and re-injected into EVERY chat request afterwards so
        # the assistant keeps personalising answers (not just the greeting).
        ctx: dict[str, str] = {
            "lang": lang,
            "locale": browser.get("lang") or "",
            "platform": browser.get("platform") or "",
            "is_windows": "1" if "Win" in (browser.get("platform") or "") else "",
            "tz": tz_name,
            "local_time": "",
            "time_of_day": time_of_day,
            "device": " ".join(
                part
                for part in (
                    browser.get("screen") or "",
                    f"{browser.get('cores')} cores" if browser.get("cores") else "",
                    f"{browser.get('mem')} GiB RAM" if browser.get("mem") else "",
                    "online" if browser.get("online") else "offline",
                )
                if part
            ),
        }
        if local_epoch_s:
            try:
                ctx["local_time"] = datetime.fromtimestamp(
                    local_epoch_s, ZoneInfo(tz_name)
                ).strftime("%H:%M")
            except Exception:  # noqa: BLE001
                ctx["local_time"] = ""
        if geo.get("city") and geo.get("country"):
            ctx["location"] = f"{geo['city']}, {geo['country']}"
        elif geo.get("country"):
            ctx["location"] = geo["country"]
        logger.info("greeting: ctx=%r", ctx)

        # Weather for their location (best-effort, open-meteo, no key).
        weather = await _weather_lookup(geo.get("lat", ""), geo.get("lon", ""))
        logger.info("greeting: weather=%r", weather)
        for key in (
            "word", "temp", "feels_like", "humidity", "precip",
            "pressure", "wind", "is_day", "warning",
        ):
            if weather.get(key):
                ctx[key] = str(weather[key])
        if weather.get("word"):
            ctx["weather"] = f"{weather['word']} {weather.get('emoji', '')}"
        ctx["sunrise"] = weather.get("sunrise", "")
        ctx["sunset"] = weather.get("sunset", "")
        ctx["moon"] = weather.get("moon", "")
        ctx["moon_emoji"] = weather.get("moon_emoji", "")
        self.visitor_context = ctx

        # Flags: prefer country flag (precise, from the IP geo), fall back to
        # the device-language flag.
        country_flag = _country_flag(geo.get("country_code", ""))
        lang_flag = _language_flag(lang)
        flag = country_flag or lang_flag
        is_windows = bool(ctx["is_windows"])
        location = ctx.get("location", "")
        logger.info("greeting: flag=%r country_flag=%r lang_flag=%r location=%r windows=%r", flag, country_flag, lang_flag, location, is_windows)

        self.messages.append({"role": "assistant", "content": ""})
        yield
        is_admin_greet = self.is_admin
        is_returning = bool(self.user_email) and not is_admin_greet
        client = get_chat_client()
        if client is None:
            # AI disabled or not configured - use fallback greeting
            if is_admin_greet:
                self.messages[-1]["content"] = (
                    "Welcome back, Frank. Everything's running — the dashboard is ready whenever you want it."
                )
            elif is_returning:
                self.messages[-1]["content"] = (
                    "Welcome back! Good to see you again. What can I help you with?"
                )
            else:
                self.messages[-1]["content"] = (
                    "Hi! I'm Frank's assistant. Ask me anything about Frank's CV. Who are you?"
                )
            _notify("AI greeting failed", "A visitor arrived but the LLM greeting failed.", ["warning"])
        else:
            try:
                if is_admin_greet:
                    greet_hook = (
                        "Now: Frank (the site owner) is signed in and opening the site. "
                        "Write a short, warm personal greeting for him in English. "
                        "Address him as the person in charge of this site. Do NOT ask who "
                        "he is, do NOT ask for an email, do NOT treat him as a stranger. "
                        "Acknowledge him as the owner comfortably and briefly."
                    )
                elif is_returning:
                    greet_hook = (
                        f"Now: a returning identified visitor ({self.user_email}) is opening "
                        f"the site. Write a short personal greeting for them in {lang} "
                        "(EVERY word in {lang}, no exceptions) that welcomes them back "
                        "warmly and naturally, mentioning that you remember them. Do not "
                        "re-ask who they are."
                    )
                else:
                    greet_hook = (
                        f"Now: you just detected a new visitor. Write a short personal "
                        f"greeting for them in {lang} (the visitor's language - EVERY word "
                        f"you write must be in {lang}, no exceptions). Make it warm and relevant."
                    )
                parts = [
                    read_doc("prompt.md"),
                    "\n\nKNOWLEDGE:\n",
                    read_doc("knowledge.md"),
                    _visitor_context_text(ctx, self.user_email, self.user_name, self.is_admin),
                    "\n\n" + greet_hook,
                ]
                if time_of_day:
                    parts.append(f" Their local time is {time_of_day}.")
                if weather.get("word"):
                    parts.append(f" The weather there is {weather['word']} {weather['emoji']}.")
                if weather.get("temp"):
                    parts.append(
                        f" Temperature: {weather['temp']}"
                        + (f" (feels like {weather['feels_like']})." if weather.get("feels_like") else ".")
                    )
                if weather.get("pressure"):
                    parts.append(f" Pressure: {weather['pressure']}.")
                if weather.get("humidity"):
                    parts.append(f" Humidity: {weather['humidity']}.")
                if weather.get("wind"):
                    parts.append(f" Wind: {weather['wind']}.")
                if weather.get("warning"):
                    parts.append(
                        f" There is a weather warning in effect: {weather['warning']}. "
                        "Mention it in a natural, non-alarmist way."
                    )
                if weather.get("sunrise") and weather.get("sunset"):
                    parts.append(
                        f" The sun there rises at {weather['sunrise']} and sets at "
                        f"{weather['sunset']} local time."
                    )
                if weather.get("moon"):
                    parts.append(
                        f" The moon there is in its {weather['moon']} phase {weather['moon_emoji']}."
                    )
                if location:
                    parts.append(f" They are in {location}.")
                if ctx.get("device"):
                    parts.append(
                        f" Their browser reports the device as: {ctx['device']}. If their setup "
                        "is noteworthy (e.g. a small phone screen, an enormous display, unusually "
                        "many cores/RAM, or being offline), you may mention it once, lightly. "
                        "Do not read a screen resolution out loud like a spec sheet."
                    )
                if lang and location:
                    parts.append(
                        f" Their browser language is {lang} and they are browsing from "
                        f"{location}. If that pairing tells an interesting story - e.g. a "
                        "Spanish speaker in France is probably on holiday, someone browsing "
                        "from their own country in their native language is likely at home - "
                        "weave ONE such smart observation into the greeting, naturally and "
                        "briefly. Never force it if nothing stands out."
                    )
                if flag and not is_windows:
                    parts.append(f" Their country flag is {flag}. Put that flag at the START of the greeting.")
                elif is_windows:
                    parts.append(
                        " They are on Windows. ONLY the country/flag emoji must be avoided "
                        "(Windows fonts cannot render regional-indicator flag emoji). Other "
                        "emoji - weather, sun, moon, temperature - are FINE and welcome. "
                        "Mention their country/region by name in plain text."
                    )
                parts.append(
                    " Craft the greeting around their local time, the sun cycle, the moon "
                    "and the weather when available (e.g. a rainy evening gets a rain emoji "
                    "and a 'cozy' note; at night, talk about the moon and when the sun will "
                    "rise; during the day, mention sunset). Mention the pressure or other "
                    "meteorological detail only if it makes the greeting feel natural. Never "
                    "say the sun is out at night or vice versa. It must "
                    "be 1-3 sentences and feel natural."
                    + (
                        " END by asking the visitor who they are."
                        if not (is_admin_greet or is_returning)
                        else " Do NOT ask who they are."
                    )
                    + " Only name their city/country if the visitor details actually provide "
                    "a location. NEVER invent or guess a city from the timezone - if you are "
                    "not told where they are, greet them warmly without naming a place. Do "
                    "not mention IP addresses, tokens, or anything sensitive."
                )
                system_content = "".join(parts)
                stream = await client.chat.completions.create(
                    model=CHAT_MODEL,
                    messages=[
                        {
                            "role": "system",
                            "content": system_content,
                        },
                        {"role": "user", "content": "Greet me now."},
                    ],
                    temperature=0.7,
                    reasoning_effort="none",
                    max_tokens=300,
                    stream=True,
                )
                chunks: list[str] = []
                async for event in stream:
                    if not event.choices:
                        continue
                    delta = event.choices[0].delta.content or ""
                    if delta:
                        chunks.append(delta)
                        self.messages[-1]["content"] = "".join(chunks)
                        yield rx.call_script(chat_scroll_js())
                logger.info("greeting: chunks=%d text=%r", len(chunks), self.messages[-1]["content"])
                if not chunks:
                    if is_admin_greet:
                        self.messages[-1]["content"] = (
                            "Welcome back, Frank. Everything's running — the dashboard is ready whenever you want it."
                        )
                    elif is_returning:
                        self.messages[-1]["content"] = (
                            "Welcome back! Good to see you again. What can I help you with?"
                        )
                    else:
                        self.messages[-1]["content"] = (
                            f"Hi! I'm Frank's assistant — welcome. I can tell you're in "
                            f"{ctx.get('location') or ctx.get('device') or 'a browser'} "
                            f"right now. Who are you?"
                        )
            except Exception:  # noqa: BLE001
                logger.exception("greeting generation failed")
                self.greeting_in_progress = False
                if is_admin_greet:
                    self.messages[-1]["content"] = (
                        "Welcome back, Frank. Everything's running — the dashboard is ready whenever you want it."
                    )
                elif is_returning:
                    self.messages[-1]["content"] = (
                        "Welcome back! Good to see you again. What can I help you with?"
                    )
                else:
                    self.messages[-1]["content"] = (
                        "Hi! I'm Frank's assistant. Ask me anything about Frank's CV. Who are you?"
                    )
                _notify("AI greeting failed", "A visitor arrived but the LLM greeting failed.", ["warning"])
        site_store.log_conv_message(
            self.conv_id, "assistant", self.messages[-1]["content"],
            self.visitor_ip, self.visitor_geo, self.user_email,
            self.visitor_id, self.visitor_context.get("device", ""),
            owner=True,
        )
        site_store.backfill_geo(self.visitor_ip, self.visitor_geo)
        greet = self.messages[-1]["content"].strip().splitlines()[0][:80]
        if not is_admin_greet and not is_returning:
            _notify(
                "New visitor",
                _visitor_notify_text(ctx, self.visitor_ip, self.visitor_geo) + f"\n\nGreeting: {greet}",
                ["wave"],
            )
        self.greeting_in_progress = False
        # Make this visitor reachable for instant chat push (idle readers too).
        self._register_visitor()
        yield rx.call_script(chat_ding_js())

    async def handle_submit(self, form_data: dict):
        # Read straight from the DOM's FormData at submit time (the input is
        # uncontrolled) so Android GBoard autocomplete can't double characters
        # by racing a server round-trip on every keystroke.
        q = str(form_data.get("question") or "").strip()
        async for event in self.ask(q):
            yield event
        # The last state flush (busy=False) re-renders the panel; put the caret
        # back in the input so the visitor can keep typing without clicking.
        yield rx.call_script(_focus_js("chat-input"))

    def note_typing(self, _value: str = ""):
        """Visitor typing heartbeat -> stamps presence for admin takeover UI."""
        if not self.conv_id:
            self.conv_id = "c_" + secrets.token_hex(6)
        site_store.touch_typing(self.conv_id)
        self._register_visitor()

    async def ask(self, q: str):
        """Run the full ask flow: append the question, notify, stream the answer."""
        if not q or self.busy:
            return
        if not self.conv_id:
            self.conv_id = "c_" + secrets.token_hex(6)
        self._register_visitor()
        self.messages.append({"role": "user", "content": q})
        site_store.log_conv_message(self.conv_id, "user", q, self.visitor_ip, self.visitor_geo, self.user_email, self.visitor_id, self.visitor_context.get("device", ""), owner=True)
        if self.conv_id not in _NOTIFIED_CONVS:
            _NOTIFIED_CONVS.add(self.conv_id)
            ip = self.visitor_ip or "unknown"
            loc = self.visitor_geo.get("city") or self.visitor_geo.get("country") or ""
            loc = loc or self.visitor_context.get("location") or "unknown location"
            _notify(
                "Visitor message",
                f"{loc}\nIP: {ip}\nQuestion: {q[:140]}",
                ["speech_balloon"],
            )
        self.busy = True
        self.messages.append({"role": "assistant", "content": ""})
        yield
        try:
            # If the thread is past the compactor threshold, the model first
            # summarises it and that summary becomes the new chat history.
            if await _compact_conversation(self.conv_id):
                logger.info("ask: history compacted for %s before answering", self.conv_id)
            history = [_system_message(self.visitor_context, self.user_email, self.user_name, self.is_admin)]
            # Inject any compacted summary (the pre-compaction transcript is
            # already replaced in the store; self.messages may still hold it).
            for m in site_store.get_conv_messages(self.conv_id) or []:
                if m.get("compacted"):
                    history.append({"role": "system", "content": m["content"]})
            history += [
                {"role": m["role"], "content": m["content"]}
                for m in self.messages[:-1]
                if m.get("role") in ("user", "assistant")
            ][-10:]
            client = get_chat_client()
            if client is None:
                self.messages[-1]["content"] = FALLBACK
                _notify("Chat backend error", "AI chat is disabled or not configured", ["warning"])
                self.busy = False
                yield rx.call_script(chat_ding_js())
                return
            # Check if admin has taken over
            if site_store.is_ai_paused(self.conv_id):
                self.messages[-1]["content"] = "(Waiting for Frank to type...)"
                yield rx.call_script(chat_scroll_js())
                self.busy = False
                return

            stream = await client.chat.completions.create(

                model=CHAT_MODEL,
                messages=history,
                temperature=0.4,
                reasoning_effort="none",
                max_tokens=2048,
                stream=True,
            )
            chunks: list[str] = []
            async for event in stream:
                if not event.choices:
                    continue
                delta = event.choices[0].delta.content or ""
                if delta:
                    chunks.append(delta)
                    self.messages[-1]["content"] = "".join(chunks)
                    yield rx.call_script(chat_scroll_js())
            draft = "".join(chunks).strip()
            ok, reason = await filter_draft(q, draft)
            if not ok:
                logger.warning("answer filtered out: %s", reason)
            self.messages[-1]["content"] = draft if ok else FALLBACK
        except Exception as exc:  # noqa: BLE001
            logger.exception("chat backend failure")
            self.messages[-1]["content"] = (
                f"(chat backend error: {exc.__class__.__name__})"
            )
            _notify("Chat backend error", f"{exc.__class__.__name__}: {q[:80]}", ["warning"])
        site_store.log_conv_message(
            self.conv_id, "assistant", self.messages[-1]["content"],
            self.visitor_ip, self.visitor_geo, self.user_email,
            self.visitor_id, self.visitor_context.get("device", ""),
            owner=True,
        )
        self.busy = False
        yield rx.call_script(chat_ding_js())

def banner() -> rx.Component | None:
    text = build_failed_marker()
    if text is None:
        return None
    return rx.box(
        text,
        color="#fca5a5",
        background="#3f1214",
        border="1px solid #7f1d1d",
        padding="0.6rem 1rem",
        borderRadius="0.5rem",
        marginBottom="1rem",
        fontFamily="monospace",
    )


def chat_message(item: dict[str, str]) -> rx.Component:
    is_user = item["role"] == "user"
    return rx.box(
        rx.cond(
            is_user,
            rx.text(item["content"], whiteSpace="pre-wrap"),
            rx.markdown(item["content"]),
        ),
        rx.cond(
            item["edited"],
            rx.text("✎ edited", color="#66708a", fontSize="0.7rem", marginTop="0.15rem"),
        ),
        rx.cond(
            ~is_user,
            rx.icon_button(
                rx.icon("copy", size=14),
                on_click=rx.set_clipboard(item["content"]),
                variant="ghost",
                size="1",
                color="#c9d2e3",
                position="absolute",
                bottom="0",
                right="0",
                margin="0.4rem",
                _hover={"color": "#fff", "background": "rgba(255, 255, 255, 0.1)"}
            )
        ),
        position="relative",
        alignSelf=rx.cond(is_user, "flex-end", "flex-start"),
        background=rx.cond(is_user, "#1f2937", "#182032"),
        color="#e8ecf4",
        border="1px solid #2f3b52",
        borderRadius="0.8rem",
        padding="0.6rem 0.9rem",
        paddingBottom=rx.cond(~is_user, "1.8rem", "0.6rem"), # Make space for button
        maxWidth="85%",
    )


def suggestion_chip(q: str) -> rx.Component:
    """One clickable example-question chip (asks the question on click)."""
    return rx.el.button(
        q,
        type="button",
        disabled=State.busy,
        on_click=[State.ask(q), rx.call_script(_focus_js("chat-input"))],
        style={
            "background": "transparent",
            "color": MUTED,
            "border": "1px solid #2a3247",
            "borderRadius": "1rem",
            "padding": "0.45rem 0.85rem",
            "fontFamily": "inherit",
            "fontSize": "0.8rem",
            "cursor": "pointer",
            "textAlign": "left",
        },
    )


def chat_panel() -> rx.Component:
    return rx.box(
        rx.heading("Ask the site", size="2", color="#e8ecf4", marginBottom="1rem"),
        rx.vstack(
            rx.foreach(State.messages, chat_message),
            id="chat-log",
            spacing="3",
            width="100%",
            overflowY="auto",
            maxHeight="45vh",
        ),
        rx.cond(
            State.show_suggestions,
            rx.hstack(
                rx.foreach(State.suggestions, suggestion_chip),
                spacing="2",
                marginTop="0.75rem",
                style={"flexWrap": "wrap"},
            ),
        ),
        rx.el.form(
            rx.hstack(
                rx.el.input(
                    name="question",
                    id="chat-input",
                    placeholder="Ask something about this site...",
                    auto_complete="off",
                    auto_capitalize="off",
                    on_change=State.note_typing,
                    style={
                        "flex": "1",
                        "background": "#0d1117",
                        "color": "#e8ecf4",
                        "border": "1px solid #2a3247",
                        "borderRadius": "0.5rem",
                        "padding": "0.6rem 0.8rem",
                        "fontFamily": "inherit",
                    },
                ),
                rx.button(
                    "Send",
                    type="submit",
                    disabled=State.busy,
                    background=ACCENT,
                    color="#0b0e14",
                    fontWeight="600",
                ),
                spacing="2",
                width="100%",
            ),
            on_submit=[
                State.handle_submit,
                rx.call_script(_focus_js("chat-input")),
            ],
            auto_complete="off",
            reset_on_submit=True,
            width="100%",
            marginTop="1rem",
        ),
        **CARD,
        width="min(720px, 92vw)",
    )


def chat_fab() -> rx.Component:
    """Floating action button that opens the chat popup."""
    return rx.box(
        rx.button(
            rx.hstack(
                rx.icon(tag="message-circle", size=20),
                rx.text("Chat", fontSize="0.85rem"),
                spacing="1",
                align="center",
            ),
            on_click=State.open_chat_popup,
            background=ACCENT,
            color="#0b0e14",
            fontWeight="600",
            style={
                "position": "fixed",
                "right": "1.5rem",
                "bottom": "1.5rem",
                "zIndex": 1000,
                "borderRadius": "9999px",
                "padding": "0.6rem 1rem",
                "boxShadow": "0 8px 24px rgba(0, 0, 0, 0.4)",
            },
        ),
        id="chat-fab",
    )


def chat_popup() -> rx.Component:
    """Floating chat window (renders the existing chat_panel), opened via the FAB."""
    return rx.cond(
        State.chat_popup_open,
        rx.box(
            # click-through backdrop closes the popup
            rx.box(
                position="fixed",
                inset="0",
                background="rgba(0, 0, 0, 0.55)",
                zIndex=999,
                on_click=State.close_chat_popup,
            ),
            # floating chat window, anchored opposite the FAB
            rx.box(
            chat_fab(),
            chat_popup(),
                position="fixed",
                right="1.5rem",
                bottom="6rem",
                zIndex=1000,
                maxHeight="min(80vh, 85vh)",
                overflow="auto",
                borderRadius="0.75rem",
                boxShadow="0 24px 60px rgba(0, 0, 0, 0.5)",
                background=BG,
                padding="1rem",
            ),
        ),
        rx.fragment(),
    )


def index() -> rx.Component:
    return rx.center(
        rx.vstack(
            rx.hstack(
                rx.heading(State.home_title, size="5", color="#e8ecf4"),
                auth_menu(),
                width="min(720px, 92vw)",
                justify="between",
                alignItems="center",
            ),
            work_in_progress_banner(),
            rx.markdown(State.home_intro, color=ACCENT),
            banner(),
            chat_panel(),
            rx.hstack(
                rx.link("About", href="/about", color=ACCENT),
                rx.link("CV", href="/cv", color=ACCENT),
                rx.link("Projects", href="/projects", color=ACCENT),
                rx.link("Contact", href="/contact", color=ACCENT),
                rx.link("Appointments", href="/appointments", color=ACCENT),
                spacing="4",
                fontSize="0.85rem",
                width="min(720px, 92vw)",
                justify="center",
            ),
            rx.hstack(
                rx.link("LinkedIn", href="https://www.linkedin.com/in/frankeee/", color=ACCENT, is_external=True),
                rx.link("GitHub", href="https://github.com/frankinkua", color=ACCENT, is_external=True),
                rx.text("frank-escudero.com", color=MUTED),
                spacing="4",
                fontSize="0.85rem",
                width="min(720px, 92vw)",
                justify="center",
            ),
            incident_log(),
            page_footer(),
            spacing="5",
            width="100%",
            maxWidth="760px",
            padding="2.5rem 1rem",
            align="center",
        ),
        width="100%",
        minHeight="100vh",
        background=BG,
        fontFamily="ui-monospace, Menlo, monospace",
    )


def about() -> rx.Component:
    return rx.center(
        rx.vstack(
            auth_menu(),
            rx.heading("About me", size="4", color="#e8ecf4"),
            rx.link("Back to main", href="/", color=ACCENT, fontSize="0.85rem"),
            rx.markdown(State.page_body, color="#c9d2e3"),
            page_footer(),
            spacing="4",
            width="min(860px, 92vw)",
            padding="2.5rem 1rem",
            align="center",
        ),
        width="100%",
        minHeight="100vh",
        background=BG,
        fontFamily="ui-monospace, Menlo, monospace",
    )


def cv() -> rx.Component:
    return markdown_page("Frank Escudero — CV", State.page_body)


def contact() -> rx.Component:
    return rx.center(
        rx.vstack(
            auth_menu(),
            rx.heading("Contact", size="4", color="#e8ecf4"),
            rx.link("Back to main", href="/", color=ACCENT, fontSize="0.85rem"),
            rx.markdown(State.page_body, color="#c9d2e3"),
            page_footer(),
            spacing="4",
            width="min(860px, 92vw)",
            padding="2.5rem 1rem",
            align="center",
        ),
        width="100%",
        minHeight="100vh",
        background=BG,
        fontFamily="ui-monospace, Menlo, monospace",
    )


def projects() -> rx.Component:
    return markdown_page("Projects — Frank Escudero", State.page_body)


def markdown_page(title: str, body: rx.Var[str]) -> rx.Component:
    """Shared layout for content pages: heading + markdown body + footer nav."""
    return rx.center(
        rx.vstack(
            auth_menu(),
            rx.heading(title, size="4", color="#e8ecf4"),
            rx.link("Back to main", href="/", color=ACCENT, fontSize="0.85rem"),
            rx.markdown(body, color="#c9d2e3"),
            page_footer(),
            spacing="4",
            width="min(860px, 92vw)",
            padding="2.5rem 1rem",
            align="center",
        ),
        width="100%",
        minHeight="100vh",
        background=BG,
        fontFamily="ui-monospace, Menlo, monospace",
    )


# --------------------------------------------------------------------------- #
# Auth + analytics pages
# --------------------------------------------------------------------------- #
def theme_toggle() -> rx.Component:
    """Dark / girly-light toggle. Pure client-side: flips body.cv-light, and the
    sun/moon icon swap is done in GIRLY_CSS so no Reflex state is needed."""
    return rx.button(
        rx.el.span("🌙", class_name="cv-ic-dark"),
        rx.el.span("☀️", class_name="cv-ic-light"),
        on_click=rx.call_script("window.cvToggleTheme()"),
        size="1",
        variant="outline",
        background="transparent",
        color=ACCENT,
        borderColor="#2a3247",
        aria_label="Toggle theme",
        title="Toggle light/dark theme",
    )


def auth_menu() -> rx.Component:
    """Small profile menu: sign-in links when anonymous, dropdown when signed in."""
    return rx.hstack(
        theme_toggle(),
        rx.cond(
            State.has_unread,
            rx.icon(tag="bell", color=ACCENT, size=20, on_click=State.clear_unread, cursor="pointer"),
        ),
        rx.cond(
            State.is_logged_in,
            rx.menu.root(
                rx.menu.trigger(
                    rx.button(
                        rx.hstack(
                            rx.cond(
                                State.user_avatar != "",
                                rx.image(src=State.user_avatar, width="20px", height="20px", borderRadius="50%", objectFit="cover"),
                            ),
                            rx.text(f"Hi {State.user_name} ▾"),
                            spacing="2",
                            align="center",
                        ),
                        size="1",
                        variant="outline",
                        background="transparent",
                        color=ACCENT,
                        borderColor="#2a3247",
                    ),
                ),
                rx.menu.content(
                    rx.menu.item("Home", on_click=rx.redirect("/")),
                    rx.menu.item("Profile", on_click=rx.redirect("/profile")),
                    rx.cond(
                        State.is_admin,
                        rx.menu.item("Admin dashboard", on_click=rx.redirect("/admin")),
                    ),
                    rx.menu.item("Sign out", on_click=State.do_signout),
                    background="#131826",
                    color="#e8ecf4",
                ),
            ),
            rx.hstack(
                rx.link("Sign in", href="/login", color=MUTED, fontSize="0.85rem"),
                spacing="3",
            ),
        ),
        align="center",
    )


def auth_error_box() -> rx.Component:
    return rx.cond(
        State.auth_error != "",
        rx.box(
            State.auth_error,
            color="#fca5a5",
            background="#3f1214",
            border="1px solid #7f1d1d",
            borderRadius="0.5rem",
            padding="0.5rem 0.8rem",
            width="100%",
            fontSize="0.85rem",
        ),
    )


def _auth_input(name: str, placeholder: str, type_: str = "text") -> rx.Component:
    return rx.el.input(
        name=name,
        placeholder=placeholder,
        type=type_,
        required=True,
        auto_complete="on",
        style={
            "width": "100%",
            "background": "#0d1117",
            "color": "#e8ecf4",
            "border": "1px solid #2a3247",
            "borderRadius": "0.5rem",
            "padding": "0.6rem 0.8rem",
            "fontFamily": "inherit",
        },
    )


def login_page() -> rx.Component:
    return rx.center(
        rx.vstack(
            auth_menu(),
            rx.heading("Sign in", size="4", color="#e8ecf4"),
            rx.text("Sign in to get updates from this site.", color=MUTED, fontSize="0.85rem"),
            rx.el.form(
                rx.vstack(
                    _auth_input("email", "email", "email"),
                    _auth_input("password", "password", "password"),
                    rx.button("Sign in", type="submit", background=ACCENT, color="#0b0e14", fontWeight="600"),
                    spacing="3",
                    width="100%",
                ),
                on_submit=State.do_login,
                width="100%",
            ),
            auth_error_box(),
            rx.hstack(
                rx.link("Back to main", href="/", color=MUTED, fontSize="0.85rem"),
                rx.spacer(),
                rx.link("Create an account", href="/signup", color=ACCENT, fontSize="0.85rem"),
                spacing="4",
            ),
            page_footer(),
            spacing="4",
            width="min(420px, 92vw)",
            padding="2.5rem 1rem",
            align="center",
        ),
        width="100%",
        minHeight="100vh",
        background=BG,
        fontFamily="ui-monospace, Menlo, monospace",
    )


def signup_page() -> rx.Component:
    return rx.center(
        rx.vstack(
            auth_menu(),
            rx.heading("Create account", size="4", color="#e8ecf4"),
            rx.text("Signing up subscribes you to updates from this site.", color=MUTED, fontSize="0.85rem"),
            rx.el.form(
                rx.vstack(
                    _auth_input("name", "name (optional)"),
                    _auth_input("email", "email", "email"),
                    _auth_input("password", "password (min 8 chars)", "password"),
                    _auth_input("confirm", "confirm password", "password"),
                    rx.button("Sign up", type="submit", background=ACCENT, color="#0b0e14", fontWeight="600"),
                    spacing="3",
                    width="100%",
                ),
                on_submit=State.do_signup,
                width="100%",
            ),
            auth_error_box(),
            rx.hstack(
                rx.link("Already have an account? Sign in", href="/login", color=ACCENT, fontSize="0.85rem"),
                rx.link("Back to main", href="/", color=MUTED, fontSize="0.85rem"),
                spacing="4",
            ),
            page_footer(),
            spacing="4",
            width="min(420px, 92vw)",
            padding="2.5rem 1rem",
            align="center",
        ),
        width="100%",
        minHeight="100vh",
        background=BG,
        fontFamily="ui-monospace, Menlo, monospace",
    )


def avatar_crop_editor() -> rx.Component:
    """Circular viewport for panning the freshly uploaded picture into place."""
    return rx.box(
        rx.box(
            rx.image(
                src=State.avatar_pending,
                id="avatar-crop-img",
                style={
                    "position": "absolute",
                    "left": "50%",
                    "top": "50%",
                    "width": "200%",
                    "height": "200%",
                    "maxWidth": "none",
                    "maxHeight": "none",
                    "objectFit": "cover",
                    "transform": "translate(-50%, -50%)",
                    "userSelect": "none",
                    "pointerEvents": "none",
                },
            ),
            id="avatar-crop-view",
            style={
                "width": "220px",
                "height": "220px",
                "borderRadius": "50%",
                "overflow": "hidden",
                "position": "relative",
                "cursor": "grab",
                "touchAction": "none",
                "userSelect": "none",
                "background": "#1e293b",
            },
        ),
        style={
            "border": "2px solid #3b82f6",
            "borderRadius": "50%",
            "display": "inline-block",
            "lineHeight": "0",
        },
    )


def profile_page() -> rx.Component:
    return rx.center(
        rx.vstack(
            auth_menu(),
            rx.heading("Profile", size="4", color="#e8ecf4"),
            rx.cond(
                State.is_logged_in,
                rx.vstack(
                    rx.box(
                        rx.vstack(
                            rx.center(
                                rx.vstack(
                                    rx.cond(
                                        State.is_editing_avatar,
                                        avatar_crop_editor(),
                                        rx.cond(
                                            State.user_avatar != "",
                                            rx.image(src=State.user_avatar, width="100px", height="100px", borderRadius="50%", border="2px solid #3b82f6", objectFit="cover"),
                                            rx.box(
                                                rx.icon("user", size=48, color="#94a3b8"),
                                                width="100px", height="100px", borderRadius="50%", border="2px solid #2a3247",
                                                display="flex", alignItems="center", justifyContent="center", background="#1e293b"
                                            )
                                        ),
                                    ),
                                    rx.cond(
                                        State.is_editing_avatar,
                                        rx.vstack(
                                            rx.text("Drag to position · scroll or +/− to zoom", color=MUTED, fontSize="0.75rem"),
                                            rx.hstack(
                                                rx.button("-", size="1", variant="outline", color=MUTED, width="2rem", on_click=rx.call_script(zoom_avatar_js(-0.25))),
                                                rx.button("+", size="1", variant="outline", color=MUTED, width="2rem", on_click=rx.call_script(zoom_avatar_js(0.25))),
                                                spacing="2",
                                                align="center",
                                            ),
                                            rx.hstack(
                                                rx.button(
                                                    "Save Picture",
                                                    size="1",
                                                    background=ACCENT,
                                                    color="#0b0e14",
                                                    on_click=rx.call_script(crop_avatar_js(), callback=State.save_avatar_cropped),
                                                ),
                                                rx.button(
                                                    "Cancel",
                                                    size="1",
                                                    variant="outline",
                                                    color=MUTED,
                                                    on_click=State.cancel_avatar_edit,
                                                ),
                                                rx.cond(
                                                    State.avatar_saved,
                                                    rx.text("Saved ✓", color=ACCENT, fontSize="0.8rem"),
                                                ),
                                                spacing="2",
                                                align="center",
                                            ),
                                            spacing="2",
                                            align="center",
                                        ),
                                        rx.vstack(
                                            rx.el.style("#avatar_upload{border:none !important;padding:0.5rem !important;}"),
                                            rx.upload(
                                                rx.button("Upload Picture", variant="outline", size="1", color=MUTED, cursor="pointer"),
                                                id="avatar_upload",
                                                multiple=False,
                                                accept={
                                                    "image/png": [".png"],
                                                    "image/jpeg": [".jpg", ".jpeg"],
                                                    "image/webp": [".webp"]
                                                },
                                                max_files=1,
                                                on_drop=State.handle_avatar_upload(rx.upload_files(upload_id="avatar_upload")),
                                            ),
                                            rx.cond(
                                                State.avatar_error != "",
                                                rx.text(State.avatar_error, color="#fca5a5", fontSize="0.75rem"),
                                            ),
                                            spacing="2",
                                            align="center",
                                        ),
                                    ),
                                    spacing="2",
                                    align="center"
                                ),
                                width="100%",
                                paddingBottom="1rem",
                                borderBottom="1px solid #2a3247",
                                marginBottom="1rem"
                            ),
                            rx.cond(
                                State.is_editing_profile,
                                rx.form(
                                    rx.vstack(
                                        rx.text("Name", color=MUTED, fontSize="0.8rem"),
                                        rx.input(name="name", default_value=State.user_name, background="#0d1117", borderColor="#2a3247", color="#e8ecf4", width="100%"),
                                        rx.hstack(
                                            rx.button("Save", type="submit", size="1", background=ACCENT, color="#0b0e14"),
                                            rx.button("Cancel", type="button", size="1", variant="outline", on_click=State.toggle_edit_profile, color=MUTED),
                                            spacing="2",
                                        ),
                                        width="100%",
                                        align_items="flex-start"
                                    ),
                                    on_submit=State.save_profile_name,
                                    width="100%"
                                ),
                                rx.hstack(
                                    rx.text("name", color=MUTED, fontSize="0.8rem"),
                                    rx.hstack(
                                        rx.text(State.user_name, color="#c9d2e3"),
                                        rx.icon("pencil", size=14, color=MUTED, cursor="pointer", on_click=State.toggle_edit_profile),
                                        spacing="2",
                                        align="center"
                                    ),
                                    justify="between",
                                    width="100%",
                                )
                            ),
                            rx.hstack(
                                rx.text("email", color=MUTED, fontSize="0.8rem"),
                                rx.text(State.user_email, color="#c9d2e3"),
                                justify="between",
                                width="100%",
                                marginTop="0.5rem"
                            ),
                            rx.hstack(
                                rx.text("role", color=MUTED, fontSize="0.8rem"),
                                rx.text(State.user_role, color="#c9d2e3"),
                                justify="between",
                                width="100%",
                            ),
                            rx.hstack(
                                rx.text("updates", color=MUTED, fontSize="0.8rem"),
                                rx.text("on", color=ACCENT),
                                justify="between",
                                width="100%",
                            ),
                            spacing="2",
                            width="100%",
                        ),
                        background="#131826",
                        border="1px solid #2a3247",
                        borderRadius="0.5rem",
                        padding="1.5rem 1rem",
                        width="100%",
                    ),
                    rx.cond(
                        State.is_admin,
                        rx.link("Open admin dashboard", href="/admin", color=ACCENT, fontSize="0.85rem"),
                    ),
                    rx.button("Sign out", on_click=State.do_signout, background="#3b82f6", color="#0b0e14", fontWeight="600", width="100%"),
                    spacing="3",
                    width="100%",
                ),
                rx.vstack(
                    rx.text("Sign in to view your profile.", color=MUTED, fontSize="0.85rem"),
                    rx.link("Sign in", href="/login", color=ACCENT, fontSize="0.85rem"),
                    spacing="3",
                ),
            ),
            page_footer(),
            spacing="4",
            width="min(420px, 92vw)",
            padding="2.5rem 1rem",
            align="center",
        ),
        width="100%",
        minHeight="100vh",
        background=BG,
        fontFamily="ui-monospace, Menlo, monospace",
    )


def admin_table(rows, key_col: str, val_col: str, empty_text: str) -> rx.Component:
    return rx.cond(
        rows.length() == 0,
        rx.text(empty_text, color=MUTED, fontSize="0.8rem"),
        rx.vstack(
            rx.foreach(
                rows,
                lambda row: rx.hstack(
                    rx.text(row[key_col], color="#c9d2e3", fontSize="0.85rem", flex="1"),
                    rx.text(row[val_col], color=ACCENT, fontSize="0.85rem", fontWeight="600"),
                    justify="between",
                    width="100%",
                    background="#131826",
                    border="1px solid #2a3247",
                    borderRadius="0.5rem",
                    padding="0.5rem 0.9rem",
                ),
            ),
            spacing="2",
            width="100%",
        ),
    )


def admin_visit_list() -> rx.Component:
    return rx.cond(
        State.admin_visits.length() == 0,
        rx.text("No visits recorded yet.", color=MUTED, fontSize="0.8rem"),
        rx.vstack(
            rx.foreach(
                State.admin_visits,
                lambda v: rx.hstack(
                    rx.text(v["ts"], color=MUTED, fontSize="0.75rem", flex="1"),
                    rx.text(v["path"], color="#c9d2e3", fontSize="0.8rem"),
                    rx.text(v["where"], color=ACCENT, fontSize="0.8rem"),
                    rx.text(v["ip"], color=MUTED, fontSize="0.75rem"),
                    justify="between",
                    width="100%",
                    background="#131826",
                    border="1px solid #2a3247",
                    borderRadius="0.5rem",
                    padding="0.45rem 0.9rem",
                    flexWrap="wrap",
                ),
            ),
            spacing="2",
            width="100%",
        ),
    )


def pager(page, total, on_prev, on_next) -> rx.Component:
    """Prev / Next + "Page X / Y" for a paginated admin list."""
    return rx.hstack(
        rx.button("← Prev", size="1", variant="outline", color=MUTED,
                  on_click=on_prev, disabled=(page <= 0)),
        rx.text("Page ", page + 1, " / ", total, color=MUTED, fontSize="0.8rem"),
        rx.button("Next →", size="1", variant="outline", color=MUTED,
                  on_click=on_next, disabled=((page + 1) >= total)),
        justify="center", width="100%", spacing="2",
    )


def thread_card(t, takeover: bool = True) -> rx.Component:
    """One conversation card: owner + identity, status, and the last 4 messages
    (clamped to 120 chars/line, 4 lines) — a single preview block per thread."""
    return rx.box(
        rx.hstack(
            rx.text(t["owner"], color=ACCENT, fontSize="0.85rem", fontWeight="600", flex="1"),
            rx.text(t["status"], color=MUTED, fontSize="0.7rem"),
            rx.cond(
                t["ai_paused"] == "true",
                rx.text("AI paused", color="#f59e0b", fontSize="0.7rem"),
                rx.box(),
            ),
            rx.cond(
                takeover,
                rx.button("Take Over Chat", size="1", background="#3b82f6", color="#0b0e14",
                          on_click=State.set_active_live_chat(t["id"])),
                rx.box(),
            ),
            justify="between", width="100%", flexWrap="wrap", spacing="2",
        ),
        rx.text(t["identity"], " · ", t["msg_count"], " msgs", color=MUTED, fontSize="0.75rem", marginTop="0.2rem"),
        rx.box(
            rx.text(t["preview"], color="#c9d2e3", fontSize="0.8rem", whiteSpace="pre-wrap"),
            background="#0d1117",
            border="1px solid #2a3247",
            borderRadius="0.4rem",
            padding="0.5rem 0.7rem",
            marginTop="0.4rem",
            width="100%",
        ),
        rx.text("last message ", t["last_seen"], color=MUTED, fontSize="0.7rem", marginTop="0.3rem"),
        background="#131826",
        border="1px solid #2a3247",
        borderRadius="0.5rem",
        padding="0.5rem 0.9rem",
        width="100%",
    )


def admin_threads_list(takeover: bool = True) -> rx.Component:
    """The shared Conversations / Live-Chats thread list, paginated."""
    return rx.vstack(
        rx.cond(
            State.admin_threads_page.length() == 0,
            rx.text("No conversations recorded yet.", color=MUTED, fontSize="0.8rem"),
            rx.vstack(
                rx.foreach(State.admin_threads_page, lambda t: thread_card(t, takeover)),
                spacing="2",
                width="100%",
            ),
        ),
        pager(
            State.admin_thread_page,
            State.admin_thread_pages,
            State.admin_threads_prev,
            State.admin_threads_next,
        ),
        width="100%",
    )


def admin_users_list() -> rx.Component:
    """Registered users + guests: Name, Email, Location, Description, each with
    their most recent chat thread attached (last 4 messages, clamped)."""
    return rx.vstack(
        rx.cond(
            State.admin_users_page.length() == 0,
            rx.text("No users recorded yet.", color=MUTED, fontSize="0.8rem"),
            rx.vstack(
                rx.foreach(
                    State.admin_users_page,
                    lambda u: rx.box(
                        rx.hstack(
                            rx.text(u["name"], color=ACCENT, fontSize="0.85rem", fontWeight="600", flex="1"),
                            rx.text(u["email"], color="#c9d2e3", fontSize="0.8rem"),
                            rx.text(u["role"], color=MUTED, fontSize="0.7rem"),
                            rx.cond(
                                u["guest"] == "True",
                                rx.text("guest", color="#94a3b8", fontSize="0.7rem"),
                                rx.box(),
                            ),
                            justify="between", width="100%", flexWrap="wrap", spacing="2",
                        ),
                        rx.hstack(
                            rx.text("Location:", color=MUTED, fontSize="0.75rem"),
                            rx.text(u["location"], color="#c9d2e3", fontSize="0.75rem", flex="1"),
                            width="100%",
                        ),
                        rx.hstack(
                            rx.text("Description:", color=MUTED, fontSize="0.75rem"),
                            rx.text(u["description"], color="#c9d2e3", fontSize="0.75rem", flex="1"),
                            width="100%",
                        ),
                        rx.cond(
                            u["thread"] != "",
                            rx.box(
                                rx.text(u["thread"], color="#c9d2e3", fontSize="0.8rem", whiteSpace="pre-wrap"),
                                background="#0d1117",
                                border="1px solid #2a3247",
                                borderRadius="0.4rem",
                                padding="0.5rem 0.7rem",
                                marginTop="0.4rem",
                                width="100%",
                            ),
                            rx.box(),
                        ),
                        rx.text("last seen ", u["last_seen"], " · ", u["msgs"], " msgs", color=MUTED, fontSize="0.7rem", marginTop="0.3rem"),
                        background="#131826",
                        border="1px solid #2a3247",
                        borderRadius="0.5rem",
                        padding="0.5rem 0.9rem",
                        width="100%",
                    ),
                ),
                spacing="2",
                width="100%",
            ),
        ),
        pager(
            State.admin_user_page,
            State.admin_user_pages,
            State.admin_users_prev,
            State.admin_users_next,
        ),
        width="100%",
    )


def doc_editor() -> rx.Component:
    """Admin-only WYSIWYG editor: markdown textarea with live preview + save."""
    return rx.vstack(
        rx.hstack(
            rx.text("Editing", color=MUTED, fontSize="0.8rem"),
            rx.text(State.editing_doc, color=ACCENT, fontSize="0.8rem", fontWeight="600"),
            spacing="2",
            width="100%",
        ),
        rx.vstack(
            rx.text("Markdown", color=MUTED, fontSize="0.75rem"),
            rx.text_area(
                value=State.doc_edit_source,
                on_change=State.set_doc_edit_source,
                min_height="340px",
                width="100%",
                background="#0d1117",
                color="#e8ecf4",
                borderColor="#2a3247",
                fontFamily="ui-monospace, Menlo, monospace",
            ),
            spacing="2",
            width="100%",
        ),
        rx.vstack(
            rx.text("Live preview", color=MUTED, fontSize="0.75rem"),
            rx.box(
                rx.markdown(State.doc_edit_source, color="#c9d2e3"),
                width="100%",
                minHeight="200px",
                background="#0d1117",
                border="1px solid #2a3247",
                borderRadius="0.5rem",
                padding="0.8rem",
            ),
            spacing="2",
            width="100%",
        ),
        rx.hstack(
            rx.button("Save page", on_click=State.save_doc, background="#3b82f6", color="#0b0e14"),
            rx.button("Close", on_click=State.close_doc_editor, variant="outline", color=MUTED),
            rx.cond(State.doc_saved, rx.text("Saved ✓", color="#4ade80", fontSize="0.8rem")),
            spacing="3",
            width="100%",
        ),
        spacing="4",
        width="100%",
    )


def admin_doc_row(d: dict[str, object]) -> rx.Component:
    """One clickable row in the Pages file-manager list."""
    return rx.hstack(
        rx.icon("file-text", size=16, color=MUTED),
        rx.text(d["name"], color="#c9d2e3", fontSize="0.85rem", flex="1"),
        rx.cond(
            d["public"],
            rx.box("page", color=ACCENT, border="1px solid #25633f", background="#0f2a1c", borderRadius="0.75rem", padding="0 0.4rem", fontSize="0.65rem", lineHeight="1.5"),
            rx.box("doc", color=MUTED, border="1px solid #2a3247", background="#131826", borderRadius="0.75rem", padding="0 0.4rem", fontSize="0.65rem", lineHeight="1.5"),
        ),
        rx.text(d["size_label"], color=MUTED, fontSize="0.75rem"),
        rx.button(
            "Edit",
            size="1",
            variant="outline",
            color=MUTED,
            on_click=State.open_doc_editor(d["name"]),
        ),
        width="100%",
        padding="0.5rem 0.75rem",
        background="#131826",
        border="1px solid #2a3247",
        borderRadius="0.5rem",
        marginBottom="0.4rem",
        align="center",
        cursor="pointer",
        _hover={"background": "#182032", "borderColor": "#3b82f6"},
    )


def admin_page() -> rx.Component:
    return rx.center(
        rx.vstack(
            auth_menu(),
            rx.heading("Admin dashboard", size="4", color="#e8ecf4"),
            rx.cond(
                State.is_admin,
                rx.tabs.root(
                    rx.tabs.list(
                        rx.tabs.trigger("Summary", value="summary"),
                        rx.tabs.trigger("Users", value="users"),
                        rx.tabs.trigger("Visits", value="visits"),
                        rx.tabs.trigger("Chats", value="chats"),
                        rx.tabs.trigger("Pages", value="pages"),
                        rx.tabs.trigger("System", value="system"),
                    ),
                    rx.tabs.content(
                        rx.vstack(
                            rx.hstack(
                                *[
                                    rx.box(
                                        rx.vstack(
                                            rx.text(label, color=MUTED, fontSize="0.75rem"),
                                            rx.text(State.admin_stats[key], color="#e8ecf4", fontSize="1.4rem", fontWeight="700"),
                                            spacing="1",
                                        ),
                                        background="#131826",
                                        border="1px solid #2a3247",
                                        borderRadius="0.5rem",
                                        padding="1rem",
                                        flex="1",
                                    ) for label, key in [
                                        ("Visits", "total"),
                                        ("Unique Visitors", "unique"),
                                        ("Unique Chats", "convs"),
                                        ("Messages", "messages")
                                    ]
                                ],
                                spacing="3",
                                width="100%",
                                flexWrap="wrap",
                            ),
                            rx.hstack(
                                rx.vstack(
                                    rx.text("Top locations", color=MUTED, fontSize="0.8rem"),
                                    admin_table(State.admin_locations, "location", "count", "No geo data yet."),
                                    flex="1",
                                    width="100%",
                                ),
                                rx.vstack(
                                    rx.text("Top pages", color=MUTED, fontSize="0.8rem"),
                                    admin_table(State.admin_pages, "path", "count", "No visits yet."),
                                    flex="1",
                                    width="100%",
                                ),
                                spacing="4",
                                width="100%",
                                alignItems="flex-start",
                                flexWrap="wrap",
                            ),
                            width="100%",
                            spacing="5",
                        ),
                        value="summary",
                    ),
                    rx.tabs.content(
                        rx.vstack(
                            rx.text("Users & guests (Name, Email, Location, Description)", color=MUTED, fontSize="0.8rem"),
                            admin_users_list(),
                            width="100%",
                        ),
                        value="users",
                    ),
                    rx.tabs.content(
                        rx.vstack(
                            rx.text("Recent visits", color=MUTED, fontSize="0.8rem"),
                            admin_visit_list(),
                            width="100%",
                        ),
                        value="visits",
                    ),
                    rx.tabs.content(
                        rx.vstack(
                            rx.hstack(
                                rx.text("Active Chat Threads", color="#e8ecf4", fontSize="1rem"),
                                rx.button("Refresh", on_click=State.refresh_live_chat, size="1", variant="outline"),
                                justify="between", width="100%"
                            ),
                            rx.cond(
                                State.active_live_chat_id == "",
                                rx.vstack(
                                    rx.text("Chat threads (one per conversation, newest activity first) — click one to take it over.", color=MUTED, fontSize="0.75rem"),
                                    admin_threads_list(takeover=True),
                                    width="100%",
                                ),
                                rx.vstack(
                                    rx.hstack(
                                        rx.text(f"Chatting in: {State.active_live_chat_id}", color=ACCENT),
                                        rx.button("Hand back to AI", on_click=State.resume_ai_chat, size="1", variant="outline", color=MUTED),
                                        justify="between", width="100%"
                                    ),
                                    rx.box(
                                        rx.foreach(
                                            State.live_chat_messages,
                                            lambda m: rx.cond(
                                                State.edit_msg_idx == m["idx"],
                                                rx.box(
                                                    rx.text_area(
                                                        value=State.edit_msg_text,
                                                        on_change=State.set_edit_msg_text,
                                                        width="100%",
                                                        background="#0d1117",
                                                        color="#e8ecf4",
                                                        borderColor="#2a3247",
                                                    ),
                                                    rx.hstack(
                                                        rx.button("Save", on_click=State.save_edit_msg, size="1", background="#3b82f6", color="#0b0e14"),
                                                        rx.button("Cancel", on_click=State.cancel_edit_msg, size="1", variant="outline", color=MUTED),
                                                        spacing="2",
                                                        marginTop="0.4rem",
                                                    ),
                                                    background="#131826",
                                                    border="1px solid #2a3247",
                                                    padding="0.5rem",
                                                    borderRadius="0.5rem",
                                                    marginBottom="0.5rem",
                                                ),
                                                rx.box(
                                                    rx.hstack(
                                                        rx.cond(
                                                            m["edited"] != "",
                                                            rx.text("✎ edited", color=MUTED, fontSize="0.7rem"),
                                                        ),
                                                        rx.cond(
                                                            m["compacted"] != "",
                                                            rx.text("📄 " + m["compacted"], color="#f59e0b", fontSize="0.7rem"),
                                                        ),
                                                        rx.text(m["content"], color="#e8ecf4", fontSize="0.85rem", whiteSpace="pre-wrap", flex="1"),
                                                        rx.button("✎", on_click=State.start_edit_msg(m["idx"]), size="1", variant="ghost", color=MUTED),
                                                        spacing="2",
                                                        align="center",
                                                        width="100%",
                                                    ),
                                                    background=rx.cond(m["role"] == "user", "#1f2937", "#0d1117"),
                                                    border="1px solid #2a3247",
                                                    padding="0.5rem",
                                                    borderRadius="0.5rem",
                                                    marginBottom="0.5rem",
                                                    alignSelf=rx.cond(m["role"] == "user", "flex-start", "flex-end")
                                                )
                                            )
                                        ),
                                        width="100%", height="400px", overflowY="auto", padding="1rem", border="1px solid #2a3247", borderRadius="0.5rem", background="#131826", id="live-chat-log"
                                    ),
                                    rx.el.form(
                                        rx.hstack(
                                            rx.el.input(name="message", placeholder="Type a message...", width="100%", background="#0d1117", borderColor="#2a3247", color="#e8ecf4"),
                                            rx.button("Send", type="submit", background=ACCENT, color="#0b0e14"),
                                            width="100%"
                                        ),
                                        on_submit=State.send_live_chat_message,
                                        auto_complete="off",
                                        reset_on_submit=True,
                                        width="100%"
                                    ),
                                    width="100%"
                                )
                            ),
                            width="100%",
                        ),
                        value="chats",
                    ),
                    rx.tabs.content(
                        rx.vstack(
                            rx.hstack(
                                rx.text("Page content editor", color="#e8ecf4", fontSize="1rem"),
                                rx.text("Pick a file to edit", color=MUTED, fontSize="0.75rem"),
                                justify="between",
                                width="100%",
                            ),
                            rx.cond(
                                State.editing_doc != "",
                                doc_editor(),
                                rx.vstack(
                                    rx.foreach(State.admin_docs, admin_doc_row),
                                    width="100%",
                                ),
                            ),
                            width="100%",
                        ),
                        value="pages",
                    ),
                    rx.tabs.content(
                        rx.vstack(
                            rx.text("Server log", color=MUTED, fontSize="0.8rem"),
                            rx.box(
                                rx.text(State.admin_log, whiteSpace="pre-wrap", color="#c9d2e3", fontSize="0.75rem"),
                                background="#0d1117",
                                border="1px solid #2a3247",
                                borderRadius="0.5rem",
                                padding="0.7rem 0.9rem",
                                width="100%",
                                overflowX="auto",
                            ),
                            width="100%",
                        ),
                        value="system",
                    ),
                    default_value="summary",
                    width="100%",
                ),
                rx.text("Restricted access.", color=MUTED),
            ),
            spacing="5",
            width="min(800px, 92vw)",
            marginTop="2rem",
            marginBottom="4rem",
        ),
        width="100%",
        minHeight="100vh",
        background=BG,
        fontFamily="ui-monospace, Menlo, monospace",
    )


async def _notify_startup() -> None:
    try:
        await notify.send(
            "CV site started",
            f"{VERSION_LABEL} · {UPDATED_LABEL} UTC\nRoutes live at https://frank-escudero.com",
            ["computer"],
        )
    except Exception:  # noqa: BLE001
        logger.exception("startup notification failed")


try:
    _boot = site_store.ensure_admin()
    if _boot:
        logger.warning("ADMIN BOOTSTRAP: email=%s password=%s (also in /web/data/.admin-bootstrap)",
                       site_store.ADMIN_EMAIL, _boot)
except Exception:  # noqa: BLE001
    logger.exception("admin bootstrap failed")

app = rx.App(
    head_components=[
        rx.el.link(rel="icon", type="image/svg+xml", href=FAVICON_SVG),
        rx.el.link(rel="apple-touch-icon", href=FAVICON_SVG),
        rx.el.meta(property="og:site_name", content="Frank Escudero CV"),
        rx.el.meta(property="og:title", content="Frank Escudero — Software Engineer CV"),
        rx.el.meta(property="og:description", content="Frank Escudero CV - Bridging deep-tech execution with strategic business growth. AI-updated software engineer."),
        rx.el.meta(property="og:type", content="website"),
        rx.el.meta(property="og:url", content="https://frank-escudero.com/"),
        rx.el.meta(property="og:image", content="https://frank-escudero.com/media/frank-og.jpg?v=1"),
        rx.el.meta(property="og:image:width", content="1200"),
        rx.el.meta(property="og:image:height", content="630"),
        rx.el.meta(property="og:image:alt", content="Frank Escudero with his horse"),
        rx.el.meta(property="og:image:type", content="image/jpeg"),
        rx.el.meta(name="twitter:card", content="summary_large_image"),
        rx.el.meta(name="twitter:title", content="Frank Escudero — Software Engineer CV"),
        rx.el.meta(name="twitter:description", content="Frank Escudero CV - Bridging deep-tech execution with strategic business growth. AI-updated software engineer."),
        rx.el.meta(name="twitter:image", content="https://frank-escudero.com/media/frank-og.jpg?v=1"),
        rx.el.meta(name="twitter:image:alt", content="Frank Escudero with his horse"),
        rx.el.meta(name="description", content="Frank Escudero CV - Bridging deep-tech execution with strategic business growth. AI-updated software engineer."),
        rx.el.style(GIRLY_CSS),
        rx.el.script(THEME_JS),
        rx.el.script(DING_JS),
    ],
)
app.add_page(index, route="/", title="Frank Escudero — Software Engineer CV", on_load=State.load_home)
app.add_page(about, route="/about", title="About — Frank Escudero", on_load=State.load_public_doc("knowledge.md"))
app.add_page(cv, route="/cv", title="CV — Frank Escudero", on_load=State.load_public_doc("cv.md"))
app.add_page(contact, route="/contact", title="Contact — Frank Escudero CV", on_load=State.load_public_doc("contact.md"))
app.add_page(projects, route="/projects", title="Projects — Frank Escudero CV", on_load=State.load_public_doc("projects.md"))
app.add_page(login_page, route="/login", title="Sign in — Frank Escudero CV", on_load=State.load_public)
app.add_page(signup_page, route="/signup", title="Sign up — Frank Escudero CV", on_load=State.load_public)
app.add_page(profile_page, route="/profile", title="Profile — Frank Escudero CV", on_load=State.load_profile)
app.add_page(admin_page, route="/admin", title="Admin — Frank Escudero CV", on_load=State.load_admin)

app.register_lifespan_task(_notify_startup)


from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import RedirectResponse


class RedirectOldDomainMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        host = request.headers.get("host", "")
        if host.endswith("cv.story-tegu.ts.net"):
            new_url = f"https://frank-escudero.com{request.url.path}"
            if request.url.query:
                new_url += f"?{request.url.query}"
            return RedirectResponse(url=new_url, status_code=301)
        return await call_next(request)


app._api.add_middleware(RedirectOldDomainMiddleware)


async def _rss(request):
    from starlette.responses import Response
    return Response(rss_xml(), media_type="application/rss+xml; charset=utf-8")


async def _sitemap(request):
    from starlette.responses import Response
    return Response(sitemap_xml(), media_type="application/xml; charset=utf-8")


async def _robots(request):
    from starlette.responses import Response
    return Response(
        "User-agent: *\nAllow: /\nSitemap: https://frank-escudero.com/sitemap.xml\n",
        media_type="text/plain; charset=utf-8",
    )


async def _appointments(request):
    from starlette.responses import RedirectResponse
    return RedirectResponse(url=APPOINTMENTS_URL, status_code=302)


def _make_whimsy_wav() -> bytes:
    """Generate a short 'music box / celesta' arpeggio WAV at import time.

    Ascending C-E-G-C with a high sparkle, each note a plucky decaying sine
    with bell overtones. No external assets, no /web/assets writes.
    """
    import io
    import math
    import struct
    import wave

    rate = 44100
    notes = [
        (523.25, 0.00, 0.24),   # C5
        (659.25, 0.12, 0.24),   # E5
        (783.99, 0.24, 0.26),   # G5
        (1046.50, 0.36, 0.30),  # C6
        (1318.51, 0.52, 0.60),  # E6 sparkle
    ]
    total = 1.08
    n = int(total * rate)
    buf = bytearray(n * 2)

    def add(note: tuple[float, float, float]) -> None:
        freq, start, dur = note
        s0 = int(start * rate)
        s1 = min(n, s0 + int(dur * rate))
        for i in range(s0, s1):
            t = (i - s0) / rate
            env = math.exp(-5.5 * t) * (1.0 - t / dur)
            w = 2 * math.pi * freq * (i / rate)
            v = (
                math.sin(w)
                + 0.35 * math.sin(2 * w)
                + 0.12 * math.sin(3 * w)
                + 0.08 * math.sin(4 * w)
            )
            cur = struct.unpack_from("<h", buf, i * 2)[0]
            cur = max(-32767, min(32767, int(cur + env * v * 0.55 * 32767)))
            struct.pack_into("<h", buf, i * 2, cur)

    for note in notes:
        add(note)
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(bytes(buf))
    return out.getvalue()


_WHIMSY_WAV = _make_whimsy_wav()


async def _whimsy_audio(request):
    from starlette.responses import Response
    return Response(
        _WHIMSY_WAV,
        media_type="audio/wav",
        headers={"Cache-Control": "public, max-age=86400"},
    )


async def _frank_picture(request):
    from starlette.responses import Response
    return Response(
        pathlib.Path("/web/media/frank.png").read_bytes(),
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=3600"},
    )


async def _frank_picture_jpg(request):
    from starlette.responses import Response
    return Response(
        pathlib.Path("/web/media/frank.jpg").read_bytes(),
        media_type="image/jpeg",
        headers={"Cache-Control": "public, max-age=3600"},
    )


async def _frank_picture_og(request):
    from starlette.responses import Response
    return Response(
        pathlib.Path("/web/media/frank-og.jpg").read_bytes(),
        media_type="image/jpeg",
        headers={"Cache-Control": "public, max-age=3600"},
    )


# Middleware to move OG tags to top of <head> for WhatsApp crawler compatibility
class OGTagOrderMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        # Add debug header to verify middleware runs
        response.headers["X-OG-Middleware"] = "active"
        if response.media_type == "text/html":
            body = b""
            async for chunk in response.body_iterator:
                body += chunk
            
            # DEBUG
            body_str = body.decode("utf-8", errors="ignore")
            print(f"[OGTagOrderMiddleware] Processing HTML, length={len(body_str)}")
            print(f"[OGTagOrderMiddleware] First 300 chars: {body_str[:300]}")
            
            # Extract all og: and twitter: meta tags
            import re
            og_tags = re.findall(r'(<meta property="og:[^"]*" content="[^"]*"\s*/?>)', body_str)
            twitter_tags = re.findall(r'(<meta name="twitter:[^"]*" content="[^"]*"\s*/?>)', body_str)
            
            print(f"[OGTagOrderMiddleware] Found {len(og_tags)} og tags, {len(twitter_tags)} twitter tags")
            for tag in og_tags + twitter_tags:
                print(f"  Tag: {tag[:100]}")
            
            if og_tags or twitter_tags:
                # Remove them from current positions
                for tag in og_tags + twitter_tags:
                    body_str = body_str.replace(tag + "\n", "").replace(tag, "")
                
                # Build new tag block
                new_tags = "\n".join(og_tags + twitter_tags)
                
                # Insert after <meta charset="utf-8"/> (handles charSet, charset, different quotes)
                new_body = re.sub(
                    r'(<meta\s+char(?:s|S)et=["\']utf-8["\']\s*/?>)',
                    r'\1\n' + new_tags + '\n',
                    body_str,
                    count=1,
                    flags=re.IGNORECASE
                )
                
                if new_body == body_str:
                    print("[OGTagOrderMiddleware] WARNING: Regex did not match!")
                    # Fallback: insert after <head>
                    new_body = re.sub(
                        r'(<head[^>]*>)',
                        r'\1\n' + new_tags + '\n',
                        body_str,
                        count=1,
                        flags=re.IGNORECASE
                    )
                    if new_body != body_str:
                        print("[OGTagOrderMiddleware] Fallback worked!")
                    else:
                        print("[OGTagOrderMiddleware] Fallback also failed!")
                
                body_str = new_body
            
            # Create new response
            from starlette.responses import HTMLResponse
            return HTMLResponse(
                content=body_str,
                status_code=response.status_code,
                headers=dict(response.headers),
                media_type="text/html"
            )
        return response


try:
    app._api.add_route("/rss", _rss)
    app._api.add_route("/sitemap.xml", _sitemap)
    app._api.add_route("/robots.txt", _robots)
    app._api.add_route("/appointments", _appointments)
    app._api.add_route("/media/frank.png", _frank_picture)
    app._api.add_route("/media/frank.jpg", _frank_picture_jpg)
    app._api.add_route("/media/frank-og.jpg", _frank_picture_og)
    app._api.add_route("/media/whimsy.wav", _whimsy_audio)
    # Add OG tag ordering middleware (must be last to wrap everything)
    app._api.add_middleware(OGTagOrderMiddleware)
except Exception:  # noqa: BLE001
    logger.warning("could not mount /rss, /sitemap.xml, /robots.txt or /appointments route", exc_info=True)
