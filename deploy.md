## Deployment: zero-trust, secured virtual environment

The website **is publicly reachable over HTTPS** at `https://frank-escudero.com`,
terminated by a Cloudflare Tunnel — there is no open public web server, no DMZ,
and no port-forwarded HTTP(S) straight from the internet onto this box:

```
https://frank-escudero.com   (public HTTPS, Cloudflare Tunnel)
        | cloudflared (token-based, runs as root)
        v
127.0.0.1:8000              (Reflex app; never binds a public interface)
```

The **app and the AI layer live in Frank's home datacenter virtual box and are
never directly internet-exposed**. Nothing inside trusts the network by default
(zero trust): the app binds `127.0.0.1` only and is reached exclusively through
the tunnel.

### Where it runs
A single hardened **LXC host** (`cv`, node `100.115.209.119`) in Frank's home
datacenter. The whole stack — KDE/Plasma over xrdp, Tailscale, Cloudflare
Tunnel, the Reflex app, and the remote LLM proxy — runs in this virtualized box.
There is **no systemd** (PID 1 = bash); services boot idempotently from a single
chain:

```
root ~/.bashrc  ->  /usr/local/bin/start-rdp-server.sh
                       sshd -> dbus -> xrdp(+sesman) -> tailscaled (-no-logs-no-support)
                       -> cloudflared -> Reflex websiteserver(:8000)
```

- **ingress (zero-trust):** Cloudflare Tunnel. (Legacy Tailscale Funnel
  `cv.story-tegu.ts.net` still exists and 301-redirects to the public domain.)
- **compute (LLM):** remote **olla proxy** `100.100.1.10:40114/olla/proxy/v1`
  (no auth), model `prism-ml/bonsai-27b`. No GPU in this LXC.
- **app:** Reflex (Python/ASGI) on `:8000`, fronted only by the tunnel.

### Built by Frank
Every service here was deployed, maintained, and designed by **Frank Escudero**.
This CV website is itself a live demonstration of that skillset:
infrastructure, the security posture you see above, and a self-generated
application — all from one box.

### Self-healing, git-rollbacked
Every change to `/web` is a git commit pushed to GitHub; any change can be
rolled back with `git -C /web log` / `git checkout`. Supervision is init-script +
`pgrep` idempotency — no systemd.