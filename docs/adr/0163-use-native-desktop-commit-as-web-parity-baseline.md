Status: accepted

# Use the Native Desktop Commit as the Web Parity Baseline

The Linux server-hosted browser version will replicate the native Tauri desktop UI and interaction contract from `origin/prototype/native-desktop-discovery-preparation@a34512c`, under `desktop/openworker/upstream/surfaces/gui` and its Tauri shell. The checked-out `main` branch's `frontend/` is not the source of truth for pixel parity. Native-only capabilities remain in scope only as explicitly documented Platform Capability Exceptions, each with an accepted web alternative, degradation, or unavailability.

## Considered Options

- Reuse the checked-out `main` frontend: rejected because it is a different legacy web surface and does not contain the native desktop screens.
- Design a separate web product: rejected because the requirement is full visual and behavioral parity.

## Consequences

- The baseline commit and any later accepted desktop changes must be tracked before parity work is updated.
- Visual regression and interaction tests must compare the Web Counterpart against the desktop reference at agreed viewports.
- Every native-only capability must be classified explicitly; silent fallbacks are not acceptable.
