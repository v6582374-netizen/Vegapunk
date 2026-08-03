---
status: accepted
---

# Use a Vegapunk-Owned Application Update Channel

Vegapunk will reuse the existing OpenWorker native application updater and release workflow, but directly modify the existing updater files so the shipped Native Desktop Application serves only Vegapunk's Product Release Channel.
The first Product Release Channel is the public Vegapunk GitHub Releases stream for signed macOS 12+ Apple Silicon Stable Releases.
OpenWorker source updates remain a manual development concern, and the application never queries the OpenWorker Source Upstream.

## Consequences

- Development Builds have no reachable Application Update path.
- Stable builds check Vegapunk GitHub Releases automatically, but download and installation require Explicit Update Acceptance.
- The current per-version dismissal behavior remains unchanged.
- The existing updater implementation, manifest generator, release workflow, signature verification, and data-continuity behavior are reused rather than replaced with a parallel system.
- Vegapunk uses its own Product Version sequence, public release artifacts, protected CI signing authority, and Release Rollback process.
- The shipped updater supports macOS 12+ Apple Silicon in the first release and does not expose Windows, Intel Mac, or preview artifacts through the Stable Release Channel.
- Skill management remains local-only and has no Skill Update lifecycle.

## Release Rollback Runbook

If a published Stable Release is faulty, mark that GitHub Release as a pre-release so the public `latest` endpoint falls back to the previous verified Stable Release.
Confirm that `releases/latest/download/latest.json` reports the previous Product Version and that its signed artifact remains downloadable before communicating the rollback.
Keep the faulty release and its tag for investigation, and publish the corrected build under a new Product Version after the cause is fixed.

## Considered Options

- Keep OpenWorker endpoints, public key, or fallback manifests.
  Rejected because an installed Vegapunk application must never be able to replace itself with an OpenWorker release.
- Build a new updater or introduce a runtime adapter layer.
  Rejected because the existing updater implementation already provides the required behavior and a second system would increase drift and maintenance.
- Make user updates entirely manual.
  Rejected because Stable Builds should notify users of Vegapunk releases while preserving explicit download and installation consent.
- Keep background pre-download after a release is detected.
  Rejected because detecting a release must not download a complete replacement before the user accepts the update.
