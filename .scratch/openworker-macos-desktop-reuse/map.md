# OpenWorker 原生 Prompt 库设置模块决策地图

Type: map
Status: open
Labels: wayfinder:map

## Destination

Produce an implementation-ready V1 specification for adding a Native Desktop Prompt Library Module to OpenWorker System Settings.
The module must expose Vegapunk's existing core Prompt Library through its API while feeling native to OpenWorker's unchanged visual and interaction system.

## Notes

- This map is planning-only and does not authorize source copying or product implementation.
- The selected upstream baseline remains `3766805d10586c19f83cc9132de8c7e1894c24c7`.
- The complete OpenWorker source may be directly adapted after its imported baseline; adaptation commits, not a permanently untouched directory, distinguish local changes from upstream history.
- The module operates on Vegapunk's authoritative Registered Prompts through an API rather than copying a second Prompt Library into OpenWorker.
- V1 includes only the core Prompt Library: browse, search, inspect, edit, validate, and explicitly save existing Registered Prompts.
- Registered Prompt creation, deletion, renaming, and system-maintained metadata editing remain unavailable.
- Chinese Prompt Mirrors, automatic translation, translation instructions, batch translation, and synchronization are excluded.
- Saving a Prompt affects only later Vegapunk work; work already running keeps its launch-time Prompt snapshot.
- The UI must be redesigned in OpenWorker's existing settings vocabulary; the current Vegapunk Web Workspace Prompt Library UI is a behavior reference, not a visual template.
- Vegapunk service startup timing, automatic launch, packaging, process lifecycle, logs, ports, and shutdown are outside this effort. The API service is assumed available when the module performs real operations.
- General macOS signing, release channels, updater replacement, application-language support, and app icon redesign are outside this effort.
- Use `grilling`, `domain-modeling`, `prototype`, and source inspection for the tickets below.
- This local Markdown tracker uses `Assignee`, `Blocked by`, and `Blocks` fields for claims and dependencies.

## Decisions so far

- [审计 OpenWorker macOS 源码边界与构建契约](issues/01-audit-openworker-macos-source-and-build-contract.md) — Pin the selected OpenWorker source baseline and preserve its complete build inputs so the Prompt Library adaptation starts from an auditable Apple Silicon macOS source contract.
- [验证 Git subtree 上游镜像与适配同步机制](issues/02-verify-git-subtree-sync-and-mirror-boundary.md) — Import and sync immutable upstream SHAs with non-squashed subtree history; direct adaptation is allowed but must remain visible in dedicated adaptation commits and provenance.
- [审计许可证、官方更新器与资源归属](issues/03-audit-license-updater-and-asset-ownership.md) — Preserve upstream legal and tracked assets, and do not accidentally ship the official OpenWorker updater path while adapting the application.
- Core Prompt Library scope — expose browsing, search, inspection, editing, validation, and explicit saving only; exclude Chinese mirrors and all translation workflows.
- Authoritative data boundary — OpenWorker connects to the existing Vegapunk Prompt Library API and edits the same Registered Prompt source used by future Vegapunk work, rather than owning a copied library.
- Runtime-lifecycle boundary — deciding when or how the Vegapunk backend starts is deferred and must not expand the current module-design effort.
- [定义 OpenWorker 设置中的核心 Prompt 库功能契约](issues/09-define-core-prompt-library-module-contract.md) — Browse by workflow and stage, search metadata and body, edit only Prompt text with explicit validated save and unsaved-change protection, load the current-version system original into a draft for reset, and isolate API failures to the module.

## Not yet specified

- The precise OpenWorker-native settings composition and unavailable-service presentation.
- The minimal Prompt Library API surface, endpoint configuration, trust boundary, system-original storage, and save contract.
- The acceptance and regression gates proving behavior, data ownership, and visual consistency.

## Out of scope

- English/Simplified Chinese application-interface support and the previously proposed language setting.
- Chinese Prompt Mirrors, model-assisted Prompt translation, translation instructions, batch translation, or synchronization back to English.
- Creating, deleting, renaming, importing, exporting, or editing system metadata for Registered Prompts.
- Copying or forking the Prompt Library into OpenWorker's local sidecar.
- Vegapunk service startup triggers, automatic desktop launch, packaging, health orchestration, port ownership, logs, process recovery, or shutdown.
- Broader Vegapunk runtime integration beyond the minimum Prompt Library API.
- Redesigning OpenWorker's overall settings information architecture or visual system.
- General macOS signing, notarization, public distribution, or Vegapunk updater-channel work.
- App icon replacement.
