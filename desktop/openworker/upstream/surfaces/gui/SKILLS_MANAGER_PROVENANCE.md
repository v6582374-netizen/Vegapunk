# Skills Manager provenance

The Desktop Skills Manager is derived from `jiweiyeah/Skills-Manager` commit `c0b16ba603d3d110e3e39d587b0a1a3a310ea464` and tree `12ede09996060fdc329362262759f3635c6bd30c`.
The exact 296-file Git tree is preserved under `skills-manager-upstream/`.
This directory is the auditable source copy and is not a second application runtime.

The React runtime copy lives under `src/skills-manager/` and is mounted by `SkillsManagerWorkspace` inside the existing Desktop React application.
The Rust commands, models, services, and test support are integrated into the existing Tauri crate.
OpenWorker continues to use `~/.config/coworker/` and its existing read-only `load_skill` behavior.
Skills Manager continues to own `~/.skills-manager/`, and all Skill mutations pass through the migrated upstream commands and services.

`skills-manager-provenance.json` is the machine-readable source of truth for every exact-copy file, Git mode, Git blob, SHA-256 digest, disposition, integrated target, integrated SHA-256 digest, and adaptation record.
The verifier reconstructs the complete Git tree from the audit directory rather than trusting the recorded file list.
The verifier also proves that all 86 upstream Tauri commands are present in the host handler and that every non-keyframe CSS selector is scoped below `.skills-manager-root`.

## Adaptations

### `frontend-runtime-relocation`

- Reason: The complete React application must run inside the existing OpenWorker frontend.
- Behavioral impact: Imports use the `@skills-manager` namespace while module behavior remains upstream-equivalent.
- Regression coverage: `npm run build`, `npm run skills-manager:test`, and per-file integrated SHA-256 verification cover this adaptation.
- Upstream sync strategy: Copy the new upstream `src` tree first, reapply only the namespace rewrite, and regenerate the manifest.

### `embedded-memory-router`

- Reason: The embedded module cannot own the shared document history.
- Behavioral impact: Skills Manager navigation remains internal to its workspace without changing OpenWorker routes.
- Regression coverage: `npm run build` plus user-owned visual navigation acceptance cover this adaptation.
- Upstream sync strategy: Reapply the `BrowserRouter` to `MemoryRouter` substitution after each upstream `App.tsx` update.

### `workspace-scoped-theme`

- Reason: The embedded module shares a document with OpenWorker.
- Behavioral impact: Theme classes and font variables affect only `.skills-manager-root`.
- Regression coverage: `npm run build`, structured CSS scope verification, and user-owned visual theme acceptance cover this adaptation.
- Upstream sync strategy: Keep upstream theme resolution logic and retarget only its DOM mutation root.

### `react-18-file-tree-ref`

- Reason: OpenWorker currently compiles against React 18 types.
- Behavioral impact: Runtime behavior is unchanged while the editor ref type matches the host compiler.
- Regression coverage: `npm run build` covers this type-only adaptation.
- Upstream sync strategy: Drop the adaptation after a host React 19 upgrade, or reapply it while React 18 remains in use.

### `scoped-tailwind-4-bundle`

- Reason: The host uses Tailwind 3 while the copied module requires Tailwind 4.
- Behavioral impact: The generated module stylesheet does not reset or recolor host UI.
- Regression coverage: `npm run skills-manager:css`, the structured CSS scope check, and generated CSS SHA-256 verification cover this adaptation.
- Upstream sync strategy: Refresh `src/skills-manager/index.css` from upstream, reapply documented runtime adaptations, then regenerate `public/skills-manager.css`.

### `tauri-host-merge`

- Reason: A Tauri process supports one host builder, command handler, plugin set, and application lifecycle.
- Behavioral impact: All upstream Skills Manager commands and services execute inside the existing OpenWorker process.
- Regression coverage: Handler verification for all 86 upstream commands, `cargo check`, and `cargo test` cover this adaptation.
- Upstream sync strategy: Merge upstream Rust modules, register every new command and plugin, and rerun handler coverage and Rust tests.

### `host-ownership-boundaries`

- Reason: The OpenWorker loader and Skills Manager mutation service own different persistence contracts.
- Behavioral impact: OpenWorker retains read-only loading while management mutations continue through upstream services.
- Regression coverage: `npm test` and `cargo test` cover the retained host contracts.
- Upstream sync strategy: Preserve both ownership paths and reject merges that redirect OpenWorker state into Skills Manager storage.

### `dormant-incomplete-features-module`

- Reason: The pinned upstream `features.rs` references a missing `LicenseInfo` type and has no callers.
- Behavioral impact: Its exact source remains auditable without adding an uncompilable dead module to the host crate.
- Regression coverage: Exact Git tree verification and `cargo check` cover this decision.
- Upstream sync strategy: Re-evaluate registration when upstream supplies the missing model or begins calling the module.

### `pinned-module-updater-version`

- Reason: OpenWorker and the embedded Skills Manager module have independent release versions.
- Behavioral impact: Skills Manager releases are compared against module version `2.1.7` instead of OpenWorker `0.1.6`.
- Regression coverage: `update_check_uses_the_pinned_skills_manager_version` covers this adaptation.
- Upstream sync strategy: Update the constant together with the pinned upstream commit and provenance record.

### `restore-cloud-sync-workflow`

- Reason: The pinned commit contains the workflow test but accidentally omits its implementation.
- Behavioral impact: The copied pull, push, retry, and conflict workflow is executable.
- Regression coverage: `src/skills-manager/services/__tests__/cloudSyncWorkflow.test.ts` and `npm run skills-manager:test` cover the restored implementation.
- Upstream sync strategy: Prefer the file from a future upstream commit once restored there, and otherwise retain the exact implementation from upstream commit `4165c6f`.

### `wechat-validation-alignment`

- Reason: The pinned frontend regex conflicts with its own test and the upstream Rust validator.
- Behavioral impact: WeChat IDs may begin with an underscore, matching backend validation.
- Regression coverage: The frontend and Rust underscore-prefixed WeChat validation tests cover this adaptation.
- Upstream sync strategy: Remove the patch after upstream aligns its frontend regex.

### `broken-projection-classification`

- Reason: Ticket 02 found Kiro and Trae projections whose symlink targets no longer exist.
- Behavioral impact: Missing targets are observable as `Broken` sync issues while real wrong-target content remains protected.
- Regression coverage: `ticket_02_broken_kiro_and_trae_gh_axi_projections_remain_sync_issues` covers this adaptation.
- Upstream sync strategy: Retain the classification unless upstream adopts equivalent broken-projection handling.

### `inventory-edge-case-fixtures`

- Reason: Cursor manifest drift and malformed frontmatter must not make local Skills disappear or appear from stale metadata.
- Behavioral impact: Directory contents remain authoritative and tolerant scanning keeps malformed-frontmatter Skills discoverable.
- Regression coverage: The two `ticket_02` scanner regression tests cover these cases.
- Upstream sync strategy: Carry the fixtures forward and resolve upstream scanner changes against these inventory contracts.

### `parallel-rust-test-home-isolation`

- Reason: A second lock-free HOME helper forced the entire Rust suite to run serially.
- Behavioral impact: Tests restore `HOME` and `USERPROFILE` after success or panic and run with Cargo's default parallelism.
- Regression coverage: A default `cargo test` run with no `RUST_TEST_THREADS` override covers this adaptation.
- Upstream sync strategy: Keep all environment-mutating tests on the shared helper and do not restore the crate-wide serial override.

### `complete-upstream-frontend-test-gate`

- Reason: The initial host script exercised only one copied upstream frontend test file.
- Behavioral impact: All 29 inherited `node:test` files run while Vitest continues to exclude them.
- Regression coverage: `npm run skills-manager:test` is the coverage for this adaptation.
- Upstream sync strategy: Keep the recursive glob so newly added upstream `node:test` files enter the gate automatically.

### `prototype-split-inventory-workspace`

- Reason: The selected Wayfinder Variant A prototype defines the OpenWorker Skills workspace information hierarchy.
- Behavioral impact: Real Skill and group records render in a persistent inventory-detail split while all upstream commands, dialogs, filters, grouping, batch actions, and Editor navigation remain available.
- Regression coverage: `npm run build`, `npm run skills-manager:test`, and user-owned visual acceptance cover this adaptation.
- Upstream sync strategy: Retain the upstream card renderer as a dormant sync baseline and reapply the inventory selection, detail projection, localized labels, and OpenWorker token styles after upstream Skills page updates.

## Verification

Run `npm run skills-manager:css` after any upstream CSS change.
Run `npm run skills-manager:verify -- --write` only when an intentional integration change requires new recorded digests.
Run `npm run skills-manager:verify` in normal CI and review flows.
Run `npm run skills-manager:test`, `npm test`, `npm run build`, `cargo fmt --check`, `cargo check`, and `cargo test` before accepting an upstream sync.
