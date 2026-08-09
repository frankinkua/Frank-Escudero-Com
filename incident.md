**Incident log — 2026-08-09: public HTTPS (Tailscale Funnel) outage**

**Symptom:** `https://cv.story-tegu.ts.net` stopped loading for anyone outside the tailnet. External clients (normal networks and Tor) hit a TLS/certificate error: the funnel ingress accepted TCP on 443 and then aborted the handshake (`unexpected eof` / `Broken pipe`). Access through Tailscale itself (`cv.story-tegu.ts.net` via MagicDNS, and other nodes on the tailnet) kept working, which made it look like a DNS/client problem at first.

**Diagnosis:** The box itself was healthy — tailnet path returned 200, DERP `fra` session fine, `tailscale serve status` correct, funnel capability granted. A multi-country check from check-host.net (19 nodes: Brazil, Germany, India, Iran, Spain, ...) showed 19/19 `Broken pipe` on the funnel ingress IPs `185.40.234.x`, proving the fault was at the Tailscale ingress relay, not our side. `tailscale down && up` and a full daemon restart did not help.

**Root cause:** Tailscale **1.102.1** shipped a Funnel regression — externally published HTTPS fails at the TLS handshake while tailnet access works. Known reports: tailscale/tailscale#20739 and #20756 (Aug 2026), plus an NVIDIA DGX forum thread confirming the downgrade to 1.98.10 fixed it.

**Fix:** Upgraded `tailscaled` to **1.102.2** (the current stable patch release that fixes the regression) via the official `.deb`, then restarted the daemon through `/usr/local/bin/start-rdp-server.sh`. Verified from outside the tailnet: **25/25 check-host.net nodes worldwide returned HTTP 200** over valid HTTPS (Austria, Germany, Japan, UK, US, Vietnam, ...).

**Prevention:** `tailscale set --auto-update=false` (also re-applied on boot in the start script) and `apt-mark hold tailscale`, so the daemon cannot silently upgrade itself into a broken build again.
