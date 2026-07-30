# Skills Manager provenance

The Desktop Skills Manager is derived from `jiweiyeah/Skills-Manager` commit `c0b16ba603d3d110e3e39d587b0a1a3a310ea464` and tree `12ede09996060fdc329362262759f3635c6bd30c`.
The exact 296-file Git tree is preserved under `skills-manager-upstream/`.
This directory is the auditable source copy and is not a second application runtime.

The React runtime copy lives under `src/skills-manager/` and is mounted by `SkillsManagerWorkspace` inside the existing Desktop React application.
Its host adaptations are limited to the import namespace, in-memory routing, React 18 ref typing, module-scoped theme state, and generated scoped CSS.

The Rust `commands`, `models`, `services`, and `test_support` sources are integrated into the existing Tauri crate.
Their plugins, managed caches, startup watchers, risk scan, deep links, capabilities, and invoke commands are registered on the existing Tauri Builder.
The copied `features.rs` is preserved but deliberately not registered because the pinned upstream file references a missing `LicenseInfo` type and has no callers.

OpenWorker continues to use `~/.config/coworker/` and its existing read-only `load_skill` behavior.
Skills Manager continues to own `~/.skills-manager/` and all Skill mutations pass through the migrated upstream commands and services.

Run `npm run skills-manager:verify` from this directory to verify every upstream path, Git blob, SHA-256 digest, disposition, and integration target.
