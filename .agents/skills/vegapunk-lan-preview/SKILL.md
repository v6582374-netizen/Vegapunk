---
name: vegapunk-lan-preview
description: Start, verify, and share the Vegapunk browser GUI over loopback and LAN. Use when launching the Vegapunk sidecar/Vite preview, giving someone a browser address, diagnosing a blank or black page, or checking that the GUI can reach authenticated APIs.
---

# Vegapunk LAN Preview

Use this workflow whenever the Vegapunk GUI is started for browser access or an address is
reported to a user. The LAN page is served by Vite; keep the sidecar bound to loopback.

## Start in order

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

## Verify before reporting an address

Check all of the following, not just the HTML status code:

```bash
LAN_IP="$(hostname -I | awk '{print $1}')"
curl -fsS -o /dev/null "http://localhost:1420/"
curl -fsS -o /dev/null "http://${LAN_IP}:1420/"
curl -fsS http://127.0.0.1:8765/v1/settings/discovery-launch >/dev/null
```

If Playwright is available, open the LAN URL and check that the body is non-empty and that there
are no page errors or console errors. A `401` burst followed by `TypeError: ... includes` means
the configured token was not available when Vite started. Stop and restart Vite after the sidecar
is ready; do not remove `--web`, and do not expose the sidecar directly on the LAN as a workaround.

## Always report both addresses

Every handoff must include both links, with explicit labels, even when the user asks for only one:

```text
本机（loopback）：http://localhost:1420/
局域网（LAN）：http://<LAN_IP>:1420/
```

Use the actual non-loopback address from `hostname -I` (or the active interface from
`ip route get 1.1.1.1`). If there are multiple usable interfaces, list each LAN address rather
than guessing which network the user is on. Never call `127.0.0.1:8765` a LAN address; that is the
loopback-only sidecar API.

Mention the relevant navigation after the links (currently `Settings → Discovery Launch`, or the
visible `Discovery` entry when that surface is exposed directly). Do not print the API token.
