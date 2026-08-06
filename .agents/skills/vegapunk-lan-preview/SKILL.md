---
name: vegapunk-lan-preview
description: Start, verify, and share the Vegapunk browser GUI or an isolated prototype over loopback, LAN, and Tailscale. Use when launching a browser preview, giving someone a preview address, diagnosing a blank or black page, or checking that the GUI can reach authenticated APIs.
---

# Vegapunk LAN Preview

Use this workflow whenever a Vegapunk GUI or isolated prototype is started for browser access or
an address is reported to a user. Every handoff must include three explicitly labeled entries:
本机预览（loopback）、局域网预览（LAN）、and Tailscale 预览. Never silently omit one. If a
Tailscale interface is unavailable, keep the labeled entry and state that it is unavailable rather
than inventing an address.

## Start in order

### Production GUI

For this checkout, prefer the managed entry point so the two processes cannot drift apart:

```bash
cd /home/vincent/Vegapunk
systemd-run --user --unit=vegapunk-preview-1420 \
  --working-directory="$PWD" \
  "$PWD/scripts/run_vegapunk_preview.sh"
```

It starts the Sidecar, waits for its health and Discovery endpoints, then starts Vite. Use the
manual sequence below only when systemd user services are unavailable.

Run these processes sequentially. The `--web` flag is required: `openworker-server` otherwise
selects the native fake runner, while `--web` selects the real Discovery worker. Do not start
sidecar and Vite in parallel when a token is configured: the sidecar may create its token after
Vite reads the dev config, leaving browser requests unauthenticated and producing a black page.

1. Start the sidecar and wait for startup completion:

   ```bash
   cd /home/vincent/Vegapunk/desktop/openworker/upstream
   .venv/bin/openworker-server --web \
     --web-dist /home/vincent/Vegapunk/desktop/openworker/upstream/surfaces/gui/dist \
     --host 127.0.0.1 --port 8765 --cwd /home/vincent/Vegapunk
   ```

   In `--web` mode an unset `COWORKER_WEB_TOKEN` is allowed and no token file is expected. If
   `COWORKER_WEB_TOKEN` is configured, wait until the configured authentication path is ready
   before starting Vite. In either case, confirm the real Web app is responding:

   ```bash
   curl -fsS http://127.0.0.1:8765/v1/discovery >/dev/null
   ```

2. Start Vite only after the sidecar/token is ready:

   ```bash
   cd /home/vincent/Vegapunk/desktop/openworker/upstream/surfaces/gui
   npm run dev -- --host 0.0.0.0
   ```

### Isolated prototype

Keep prototype files outside production GUI code and bind only the preview server to all
interfaces. Use the project's preview command when available, or a static server for a single
HTML prototype:

```bash
cd /home/vincent/Vegapunk/.prototype/<slug>
npm run dev -- --host 0.0.0.0 --port <PORT>
# or
python3 -m http.server <PORT> --bind 0.0.0.0 --directory /home/vincent/Vegapunk/.prototype/<slug>
```

Do not expose the sidecar directly on the LAN as a workaround, and do not modify production GUI
routes merely to make an isolated prototype reachable.

## Resolve the three preview addresses

Use the actual active interface instead of guessing from a hostname or container address:

```bash
PORT="<preview-port>"
LAN_IPS="$(ip -4 -o addr show scope global 2>/dev/null | awk '$2 != "tailscale0" && $2 != "Mihomo" {sub("/.*", "", $4); print $4}')"
[ -n "$LAN_IPS" ] || LAN_IPS="$(hostname -I | tr ' ' '\n' | awk '$1 !~ /^127\\./ && $1 !~ /^198\\.18\\./ && $1 !~ /^100\\.64\\./')"
LAN_IP="$(printf '%s\n' "$LAN_IPS" | head -n 1)"
TAILSCALE_IP="$(tailscale ip -4 2>/dev/null | head -n 1)"
[ -n "$TAILSCALE_IP" ] || TAILSCALE_IP="$(ip -4 -o addr show dev tailscale0 2>/dev/null | awk '{sub("/.*", "", $4); print $4; exit}')"
```

Do not use `ip route get 1.1.1.1` blindly: a proxy/VPN policy route can return a tunnel address
such as `198.18.x.x`, which is not a browser-reachable LAN address. Prefer the physical
Ethernet/Wi-Fi interface address and exclude proxy (`Mihomo`) and Tailscale interfaces.

Use these labels and URLs in every handoff:

```text
本机预览（loopback）：http://localhost:<PORT>/
局域网预览（LAN）：http://<LAN_IP>:<PORT>/
Tailscale 预览：http://<TAILSCALE_IP>:<PORT>/
```

When `TAILSCALE_IP` is empty, report `Tailscale 预览：不可用（未检测到 tailscale0 或 Tailscale 地址）`.
Do not substitute `127.0.0.1` or the sidecar address for a missing Tailscale address. If more than
one usable LAN address exists, include each LAN candidate under the LAN label rather than
guessing which network the user is on.

## Verify before reporting an address

Check all three paths, not just the HTML status code:

```bash
curl -fsS -o /dev/null "http://127.0.0.1:${PORT}/"
for candidate in $LAN_IPS; do
  curl -fsS -o /dev/null "http://${candidate}:${PORT}/"
done
[ -z "$TAILSCALE_IP" ] || curl -fsS -o /dev/null "http://${TAILSCALE_IP}:${PORT}/"
```

For the production GUI, also verify that the sidecar is ready before reporting Vite:

```bash
curl -fsS http://127.0.0.1:8765/v1/settings/discovery-launch >/dev/null
```

If Playwright is available, open the LAN URL and check that the body is non-empty and that there
are no page errors or console errors. A `401` burst followed by `TypeError: ... includes` means
the configured token was not available when Vite started. Stop and restart Vite after the sidecar
is ready; do not remove `--web`, and do not expose the sidecar directly on the LAN as a workaround.

## Always report all three addresses

Every handoff must include all three entries, with explicit labels, even when the user asks for
only one:

```text
本机预览（loopback）：http://localhost:<PORT>/
局域网预览（LAN）：http://<LAN_IP>:<PORT>/
Tailscale 预览：http://<TAILSCALE_IP>:<PORT>/
```

Never call `127.0.0.1:8765` a LAN or Tailscale address; that is the loopback-only sidecar API.
When a remote browser cannot load a link, inspect the preview server access log and report the
actual network error; a local `curl` success proves the listener works but does not prove that the
user's device can reach the network interface.

Mention the relevant navigation after the links (currently `Settings → Discovery Launch`, or the
visible `Discovery` entry when that surface is exposed directly). Do not print the API token.
