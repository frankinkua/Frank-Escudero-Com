"""Client-side probe script that Reflex evaluates via rx.call_script.

Returns a JSON string resolved as a Promise. Kept deliberately plain JS (no
intrinsics) so it works unchanged in Reflex 0.9's call_script handler.

What it reads:
  - navigator/userAgent/memory/cores/platform/languages/timezone
  - screen size + devicePixelRatio
  - touch support
  - GPU renderer (WebGL, best effort)
  - WebRTC STUN candidates -> local IP observations (may be empty on WAN)
"""

PROBE_JS = (
    "(async () => {"
    "function gpu(){"
    "  try{const c=document.createElement('canvas');const gl=c.getContext('webgl')||c.getContext('experimental-webgl');"
    "  if(!gl)return '';return (gl.getParameter(gl.getParameter(gl.VERSION).indexOf('WebGL')>=0?35724:37445))||''}catch(e){return ''}"
    "}"
    "function webrtc(){"
    "  return new Promise(res=>{"
    "    const ips=[];"
    "    if(!window.RTCPeerConnection)return res([]);"
    "    try{"
    "      const pc=new RTCPeerConnection({iceServers:[{urls:['stun:stun1.google.com:19302','stun:stun2.google.com:19302']}]});"
    "      const timeout=setTimeout(()=>{try{pc.close()}catch(e){};res(ips)},1800);"
    "      pc.onicecandidate=e=>{"
    "        if(e.candidate){"
    "          const m=/[0-9a-f:.]{7,}/i.exec(e.candidate.candidate||'');"
    "          if(m && ips.indexOf(m[0])<0 && m[0]!=='1.0.0.1')ips.push(m[0]);"
    "        }else{clearTimeout(timeout);try{pc.close()}catch(e){};res(ips)}"
    "      };"
    "      pc.createDataChannel('probe');"
    "      pc.createOffer().then(o=>pc.setLocalDescription(o)).catch(()=>{clearTimeout(timeout);res(ips)});"
    "    }catch(e){res([])}"
    "  })"
    "}"
    "const ips=await webrtc();"
    "return JSON.stringify({"
    "lang:navigator.language||'',"
    "langs:(navigator.languages||[]).join(','),"
    "tz:(Intl.DateTimeFormat().resolvedOptions().timeZone)||'',"
    "platform:navigator.platform||'',"
    "cores:navigator.hardwareConcurrency||0,"
    "mem:navigator.deviceMemory||0,"
    "online:navigator.onLine,"
    "screen:(window.screen&&screen.width)+'x'+(window.screen&&screen.height),"
    "dpr:window.devicePixelRatio||1,"
    "touch:(('ontouchstart' in window)||(navigator.maxTouchPoints>0))?1:0,"
    "gpu:gpu(),"
    "webrtc:ips,"
    "ua:navigator.userAgent||''"
    "});"
    "})()"
)

AUTO_OPEN_JS = (
    "(async () => { await new Promise(r => setTimeout(r, 1600)); return 'open'; })()"
)

# Re-engagement nudge: fires ~28s after load if the visitor never typed.
NUDGE_JS = (
    "(async () => { await new Promise(r => setTimeout(r, 28000)); return 'nudge'; })()"
)


def focus_js(sel: str) -> str:
    return f"(async () => {{ const e=document.getElementById('{sel}'); if(e) e.focus(); return 'ok'; }})()"


def scroll_js() -> str:
    return (
        "(async () => { const el=document.getElementById('chat-log');"
        " if(el) el.scrollTop=el.scrollHeight; return 'ok'; })()"
    )


# CSS for the chat window: geometry is driven by CSS custom properties so the
# drag/resize/maximize logic in CHAT_SETUP_JS can move/resize the window purely
# in the DOM, without React re-renders wiping the position.
CHAT_CSS = (
    "#chat-window{position:fixed;z-index:1000;right:1.5rem;bottom:5.5rem;"
    "width:var(--cv-w,min(360px,92vw));height:var(--cv-h,auto);max-width:92vw;}"
    "#chat-window.cv-dragged{left:var(--cv-x);top:var(--cv-y);right:auto;bottom:auto;}"
    "#chat-window.cv-max{left:1rem!important;top:1rem!important;"
    "right:1rem!important;bottom:1rem!important;width:auto!important;"
    "height:auto!important;max-width:none!important;}"
    "#chat-window.cv-max #chat-log{max-height:calc(100vh - 11rem)!important;}"
    "#chat-header{cursor:move;user-select:none;}"
    "#chat-resize{position:absolute;right:0;bottom:0;width:18px;height:18px;"
    "cursor:nwse-resize;}"
    "#chat-window .cv-icon-restore{display:none;}"
    "#chat-window.cv-max .cv-icon-restore{display:inline-flex;}"
    "#chat-window.cv-max .cv-icon-max{display:none;}"
)

# One-time setup (runs on page load) that wires drag/resize/maximize using
# event delegation on document, so it works even though the panel mounts later
# (and survives React re-renders via CSS variables + a class toggle).
CHAT_SETUP_JS = (
    "(async () => {"
    "if(window.__cvchatInit)return 'already';window.__cvchatInit=true;"
    "var drag=null,sizing=null;"
    "function win(){return document.getElementById('chat-window');}"
    "document.addEventListener('pointerdown',function(e){"
    "var w=win();if(!w)return;"
    "if(w.classList.contains('cv-max'))return;"
    "if(e.target.closest('#chat-header')&&!e.target.closest('button')){"
    "var r=w.getBoundingClientRect();"
    "drag={dx:e.clientX-r.left,dy:e.clientY-r.top};"
    "w.style.setProperty('--cv-x',r.left+'px');"
    "w.style.setProperty('--cv-y',r.top+'px');"
    "w.classList.add('cv-dragged');e.preventDefault();}"
    "else if(e.target.closest('#chat-resize')){"
    "var r2=w.getBoundingClientRect();"
    "sizing={sx:e.clientX,sy:e.clientY,w:r2.width,h:r2.height};"
    "e.preventDefault();}"
    "});"
    "document.addEventListener('pointermove',function(e){"
    "var w=win();if(!w)return;"
    "if(drag){"
    "var x=e.clientX-drag.dx,y=e.clientY-drag.dy;"
    "x=Math.max(0,Math.min(window.innerWidth-60,x));"
    "y=Math.max(0,Math.min(window.innerHeight-40,y));"
    "w.style.setProperty('--cv-x',x+'px');"
    "w.style.setProperty('--cv-y',y+'px');}"
    "else if(sizing){"
    "var nw=Math.max(260,sizing.w+(e.clientX-sizing.sx));"
    "var nh=Math.max(200,sizing.h+(e.clientY-sizing.sy));"
    "w.style.setProperty('--cv-w',nw+'px');"
    "w.style.setProperty('--cv-h',nh+'px');}"
    "});"
    "function stop(){drag=null;sizing=null;}"
    "document.addEventListener('pointerup',stop);"
    "document.addEventListener('pointercancel',stop);"
    "document.addEventListener('click',function(e){"
    "var b=e.target.closest('#chat-max');"
    "if(b){var w=win();if(w){w.classList.toggle('cv-max');e.preventDefault();}}"
    "});"
    "return 'ok';})()"
)