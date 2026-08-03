# Vegapunk Application Updater Implementation Checklist

This checklist implements ADR-0169 without introducing a parallel updater or a runtime adapter layer.
All source changes should be made directly in the existing updater and release files.

## Confirmed contract

- [x] The user-facing updater belongs to Vegapunk, not OpenWorker.
- [x] The first Product Release Channel is the public Vegapunk GitHub Releases stream.
- [x] The first channel contains Stable Releases only.
- [x] Development Builds do not check for or install Application Updates.
- [x] Stable Builds may check automatically, but download and installation require explicit user acceptance.
- [x] The current per-version “Later” behavior remains unchanged.
- [x] Update artifacts require Vegapunk signature verification before installation.
- [x] Release signing uses a protected CI secret or release environment.
- [x] Product Versions are independent of OpenWorker versions.
- [x] The first updater target is macOS 12+ Apple Silicon.
- [x] Failed updates preserve the installed version, and every stable release has a rollback path.
- [x] User data, settings, Skill files, and Keychain continuity remain inherited requirements of the existing mechanism.
- [x] Skill management and Marketplace behavior are outside this change because the product has no Skill Update lifecycle.

## Direct source and configuration changes

- [x] Update `desktop/openworker/upstream/surfaces/gui/src-tauri/tauri.conf.json` with an independent Product Version and Vegapunk updater configuration.
- [x] Keep the existing OpenWorker bundle identity and identifier for installation and data continuity while moving the update channel identity to Vegapunk.
- [x] Replace every OpenWorker updater endpoint, fallback endpoint, public key, artifact name, and release-note identity in the live application path.
- [x] Directly update `desktop/openworker/upstream/surfaces/gui/src-tauri/src/lib.rs` so the existing commands use the Vegapunk channel and remain unavailable in Development Builds.
- [x] Reuse `desktop/openworker/upstream/surfaces/gui/src/tauri.ts` and `desktop/openworker/upstream/surfaces/gui/src/components/UpdateBanner.tsx`, changing only the product-owned identity and the explicit-download behavior required by ADR-0169.
- [x] Remove dead OpenWorker updater references from shipped code instead of leaving a hidden fallback path.
- [x] Keep the existing application update command names and data flow unless a direct product requirement makes a change necessary.
- [x] Do not add a second updater module, wrapper, service, or custom update protocol.

## Build and channel isolation

- [x] Make the Development Build path omit the updater plugin and keep the updater commands disabled.
- [x] Make the Stable Build path enable only the Vegapunk Stable Release Channel.
- [x] Keep preview builds out of the first channel and define them separately only if a future product decision requires them.
- [x] Restrict the first stable artifact matrix to macOS 12+ Apple Silicon.
- [x] Ensure Windows, Intel Mac, and other platform artifacts cannot appear in the first Stable Release Channel.

## Runtime behavior

- [x] Preserve the existing automatic version check cadence for Stable Builds.
- [x] Ensure a successful check only presents version information and release notes.
- [x] Start the full artifact download only after Explicit Update Acceptance.
- [x] Preserve the current per-version “Later” dismissal behavior.
- [x] Verify the signed artifact before installation and restart only after installation succeeds.
- [x] Preserve the current application data, settings, Skill files, and Keychain paths across an update.
- [x] Ensure check, download, signature, installation, and restart failures leave the current installed version usable.

## Release workflow and signing

- [x] Reuse `desktop/openworker/upstream/packaging/make_update_manifest.py` and `desktop/openworker/upstream/.github/workflows/release.yml` as the release structure.
- [x] Replace OpenWorker repository, artifact names, release-note text, and URLs with Vegapunk values.
- [x] Make the application metadata, Git tag, manifest version, and signed artifacts use one Product Version.
- [x] Keep the release source public so users do not need GitHub authentication or an embedded token.
- [x] Store the Vegapunk updater private key only in a protected CI secret or release environment.
- [x] Require Apple signing, notarization, and updater signing secrets before a stable tag build can publish.
- [x] Reject pre-release tags from the first Stable Release Channel.
- [x] Make stable publication an explicit release action after build, signature, manifest, and installation checks pass.
- [x] Keep the previous verified Stable Release available for Release Rollback.
- [x] Define the operator action for withdrawing a faulty release and restoring the previous verified release in ADR-0169's Release Rollback Runbook.

## Verification gates

- [ ] Search the shipped configuration and bundle inputs for any OpenWorker updater URL, public key, product name, artifact name, or fallback manifest.
- [ ] Verify a Development Build performs no updater network request and exposes no update action.
- [ ] Verify a Stable Build detects a newer Vegapunk release and does not download before explicit acceptance.
- [ ] Verify same-version dismissal and newer-version reappearance using the existing UpdateBanner tests.
- [ ] Verify an invalid or missing signature blocks installation.
- [ ] Verify download, installation, and restart failures preserve the current application and local data.
- [ ] Build and inspect the signed macOS Apple Silicon artifact and its `latest.json` manifest.
- [ ] Publish a disposable test release, exercise installation and rollback, then remove the test release before stable publication.
- [ ] Run the relevant frontend tests, Rust tests, release-manifest checks, lint, and macOS packaging verification.

## Explicitly out of scope

- [ ] Do not add or restore OpenWorker automatic source-update detection.
- [ ] Do not reintroduce the removed Skill Manager Marketplace module.
- [ ] Do not invent a Skill Update mechanism for locally discovered Skills.
- [ ] Do not build a separate update service or authentication system for the first public channel.
