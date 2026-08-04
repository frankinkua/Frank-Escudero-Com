## Deployment: zero-trust, secured virtual environment

The website **is publicly reachable over HTTPS**, but only through Frank's
tailnet — there is no open public web server, no DMZ, and no port-forwarded
HTTP(S) straight from the internet onto this box:

```
https://cv.story-tegu.ts.net     (public HTTPS, terminates on Frank's tailnet)
        | Funnel (tailnet 443), authenticated tailnet client required
        v
127.0.0.1:8000                   (Reflex app; never binds a public interface)
```

The **app and the AI agent that edits this site live in Frank's home datacenter
virtual box and are never directly internet-exposed**. Nothing inside trusts the
network by default (zero trust): the app binds `127.0.0.1` only and is reached
exclusively through the Funnel.

### Where it runs
A single hardened **LXC host** (`cv`, node `100.115.209.119`) in Frank's home
datacenter. The whole stack — KDE/Plasma over xrdp, Tailscale, Ollama, the
Reflex app, and the AI employee agent — runs in this virtualized box. There is
**no systemd** (PID 1 = bash); services boot idempotently from a single chain:

```
root ~/.bashrc  ->  /usr/local/bin/start-rdp-server.sh
                       sshd -> dbus -> xrdp(+sesman) -> tailscaled (-no-logs-no-support) -> ollama(frank) -> Reflex websiteserver(:8000)
```

- **ingress (zero-trust):** Tailscale Funnel. No open public ports.
- **compute (AI):** Ollama, on-cpu (no GPU yet); chat model `qwen3.5:0.8b`,
  agent model `gemma4:latest`.
- **app:** Reflex (Python/ASGI) on `:8000`, fronted only by the Funnel.

### Built by Frank
Every service here was deployed, maintained, and designed by **Frank Escudero**.
This CV website is itself a live demonstration of that skillset:
infrastructure, the security posture you see above, and a self-generated
application — all from one box.

### Self-healing, git-rollbacked
The AI employee (`/web/opencode-worker.sh`, off by default) edits `/web` and
commits every cycle; any change can be rolled back with `git -C /web log` /
`git checkout`. Supervision is init-script + `pgrep` idempotency — no systemd.
