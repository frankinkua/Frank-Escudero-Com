#!/usr/bin/env python3
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///
import datetime
import http.server
import socket
import socketserver

HOST = "0.0.0.0"
PORT = 8000
TITLE = "web"
BODY = "this is a work in progress..."


def page() -> bytes:
    hostname = socket.gethostname()
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    html = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{TITLE}</title>
<style>
  :root {{ color-scheme: dark; }}
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    min-height: 100vh;
    display: flex; flex-direction: column;
    align-items: center; justify-content: center;
    gap: 1rem;
    background: radial-gradient(ellipse at top, #1c2333, #0b0e14);
    font-family: ui-monospace, "Cascadia Mono", Menlo, monospace;
    color: #e8ecf4;
  }}
  .card {{
    padding: 3rem 4rem; border-radius: 1rem;
    background: #131826; border: 1px solid #2a3247;
    box-shadow: 0 12px 40px rgb(0 0 0 / .5);
    text-align: center;
  }}
  h1 {{ font-size: 1.4rem; font-weight: 500; letter-spacing: .04em; }}
  .dot {{
    display: inline-block; width: .6rem; height: .6rem; border-radius: 50%;
    background: #4ade80; margin-right: .6rem;
    animation: pulse 2s ease-in-out infinite;
  }}
  @keyframes pulse {{ 50% {{ opacity: .3; }} }}
  footer {{ font-size: .75rem; color: #66708a; }}
</style>
</head>
<body>
  <main class="card">
    <h1><span class="dot"></span>{BODY}</h1>
  </main>
  <footer>{hostname} &middot; {stamp}</footer>
</body>
</html>
"""
    return html.encode()


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        body = page()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_HEAD(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()

    def log_message(self, fmt, *args):
        print(f"{self.client_address[0]} {fmt % args}", flush=True)


if __name__ == "__main__":
    with socketserver.ThreadingTCPServer((HOST, PORT), Handler) as httpd:
        httpd.serve_forever()