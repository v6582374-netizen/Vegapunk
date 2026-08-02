# Vegapunk

Vegapunk coordinates LLM-backed agents for research, discovery, memory, and experiment evaluation.

## Language

## Product Experience

**Native Desktop Application**:
The macOS application surface for Vegapunk built from a complete OpenWorker source baseline.
Version 1 targets macOS 12+ on Apple Silicon and owns the application shell, GUI language, local sidecar lifecycle, and macOS packaging.
_Avoid_: second product shell, source-upstream identity, separate client surface

**Application Module**:
A top-level capability area selected from the Native Desktop Application's module rail.
Each Application Module owns its internal navigation and central work area while remaining inside the same application shell.
_Avoid_: role-specific console, independent application, route-driven product split

**Native Desktop Discovery Module**:
The Application Module that owns Discovery Preparation, Discovery Launch execution observation, Launch history, and runtime-artifact review.
Its internal navigation owns the Discovery lifecycle instead of creating several top-level module entries.
_Avoid_: conversation draft, reusable source library, separate project application

**Native Desktop Run Gate**:
The explicit admission boundary that enables Run only after the current Native Desktop Discovery Preparation has valid sources or text, a successful Conversion, an explicitly saved Formatted Discovery Input revision, and no active Discovery Launch.
It warns before admission, freezes the selected Launch Snapshot, and leaves the Preparation editable for a later Launch.
_Avoid_: autosave launch, mutable active input, implicit background start

**Sole Researcher**:
The one person allowed to use the Version 1 product's curated research capabilities.
Every Version 1 request is implicitly theirs; the product has no sign-in, registration, invitation, account-management, or multi-user flows.
_Avoid_: Invited Researcher, public user, multi-user account

**Local Product Boundary**:
The Version 1 product runs as one Native Desktop Application with one local HTTP sidecar on a loopback interface.
It excludes public network exposure and multi-account product access; a later expansion beyond the Sole Researcher requires a separate identity and authorization decision.
_Avoid_: remote product server, multi-user account, split service deployment

**Native Desktop Discovery Preparation**:
The one editable Discovery input record owned by the Native Desktop Discovery Module in Version 1.
It owns the current individually uploaded files, text, and formatted-input revision from which the next Discovery Launch is started.
Its source files are uploaded file entries rather than folder-access permissions.
Version 1 does not expose multiple independent Preparation records.
_Avoid_: conversation draft, reusable source library, multiple project workspaces

**Native Desktop Discovery Committed Preparation State**:
The latest complete state explicitly saved by the Sole Researcher for the Native Desktop Discovery Preparation.
It includes only source entries and free-form text accepted together as one coherent state.
In-progress uploads, rejected sources, failed submissions, and unsaved text edits are transient intake attempts rather than Preparation content.
_Avoid_: partial preparation, upload draft, transient UI state

**Native Desktop Discovery Preparation Draft**:
The current unsaved working state of the Native Desktop Discovery Preparation.
It can contain newly added or deleted source entries and edited text, but it is discarded when the application restarts before an explicit save.
_Avoid_: cached preparation, autosaved state, resumable upload

**Native Desktop Discovery Preparation Save**:
The Sole Researcher's explicit action that commits the entire current Preparation Draft as one complete Saved Preparation State.
It never commits only part of the draft.
_Avoid_: per-file autosave, background persistence, upload checkpoint

**Native Desktop Discovery Empty Preparation**:
An explicitly saved current Preparation with no source entries and no free-form text.
It is a valid reset state, but it cannot be converted or run until new input is added.
_Avoid_: failed upload, deleted Preparation record, incomplete upload

**Native Desktop Discovery Preparation Reset**:
The Sole Researcher's explicit action that replaces the current Preparation with an Empty Preparation.
It clears the free-form text, source entries, Conversion draft, and saved Formatted Discovery Input revisions while leaving Discovery Launch records unchanged.
It remains available while a Current Launch runs because the Launch Snapshot is immutable and independent of the editable Preparation.
The reset is atomic: a failed reset leaves the prior Preparation unchanged rather than partially clearing it.
_Avoid_: deleting a Discovery Launch, undoing a Launch Snapshot, clearing Launch history

**Native Desktop Discovery Source Entry**:
A single individually uploaded file record within the current Native Desktop Discovery Committed Preparation State.
Its identity stays stable when its display name or position changes, so a delete action targets exactly one entry without changing other source entries.
_Avoid_: folder, file permission, reusable library item

**Native Desktop Discovery Source Intake Batch**:
A user action that adds one or more Source Entries to the current Preparation Draft.
The batch is accepted as a whole or rejected as a whole, a rejected batch creates no Source Entry, and accepted draft changes persist only after an explicit Preparation Save.
_Avoid_: partially accepted upload, background upload queue, folder import

**Native Desktop Discovery Preparation Storage**:
The Native Desktop Application-owned persistence boundary for the explicitly saved Preparation and its committed source content.
It never contains the unsaved Preparation Draft.
It survives ordinary application restarts and is independent of repository workspaces, conversations, and temporary client state.
_Avoid_: repository results directory, client draft, conversation attachment

**Native Desktop Discovery Source Validation Boundary**:
The division between accepting source bytes into a Preparation and interpreting their file contents.
Source Intake validates identity, whitelist, completeness, and non-empty content; Conversion validates whether an accepted source can be parsed for Discovery.
_Avoid_: silent source discard, conversion during upload, treating a saved source as automatically readable

**Native Desktop Discovery Source Intake**:
The Discovery Preparation input surface that accepts multiple individual files and free-form text in one submission.
Version 1 rejects folders and does not treat AccessSection folder permissions as uploaded Discovery sources.
All accepted files and text belong to the single current Native Desktop Discovery Preparation.
_Avoid_: folder upload, shared file library, session working directory

**Native Desktop Discovery RightRail Access Boundary**:
The Native Desktop Discovery Module does not render or mutate the session-level AccessSection.
Discovery's source authority is the saved Preparation's Source Entries and free-form text, not connector toggles or folder roots.
Any future credential or capability visibility uses a separate read-only Discovery summary.
_Avoid_: session connector controls in Discovery, folder permission as source intake, arbitrary filesystem browsing

**Native Desktop Discovery RightRail Progress Boundary**:
Discovery progress comes from Preparation stages or durable Launch records, never from conversation Todo items or tool-call activity.
A reopened Launch renders the same durable timeline and bounded activity, while available actions come from the server-authoritative lifecycle state.
_Avoid_: chat Todo as runtime truth, React-only progress, terminal history presented as live work

**Native Desktop Discovery RightRail Artifact Visibility**:
The Preparation view does not show an artifact list because it has no selected Discovery Launch output.
The active Launch view and a selected read-only history Launch show only artifacts owned by that Launch.
Artifact visibility never falls back to session workspaces, repository roots, or artifacts from another Launch.
_Avoid_: mixing inputs with outputs, cross-Launch artifact browsing, session artifact leakage

**Native Desktop Discovery Artifact Access Boundary**:
Discovery artifact requests use a Launch identity and a Launch-relative path that the sidecar validates against that Launch's artifact root.
Markdown, text, structured text, code, and images may use in-app viewers, while PDFs, Office files, large files, and other binaries use explicit native Open or Reveal actions.
The GUI never receives arbitrary absolute paths or filesystem browsing capability, and Raw Discovery Console remains a separate log surface.
_Avoid_: path escape, arbitrary file browser, absolute-path leakage, raw-log artifact mixing

**Native Desktop Discovery Run Policy**:
The Version 1 execution rule that permits at most one running Discovery Launch at a time while retaining completed or failed Launches as read-only history.
It does not permit parallel Discovery Launches or multiple active Preparation records.
_Avoid_: parallel runs, queued user-visible Launches, disposable run output

**Application Update**:
A user-facing replacement of the installed Native Desktop Application with a newer Vegapunk release selected by the Product Release Channel.
It does not import OpenWorker source changes or modify the source baseline.
_Avoid_: source synchronization, OpenWorker update, Git sync

**Product Release Channel**:
The Vegapunk-owned authority from which eligible releases of the Native Desktop Application are offered to users.
Its first release source is Vegapunk's own GitHub Releases, and it is independent of the OpenWorker Source Upstream.
Its first product stream is a single Stable Release Channel, and it is the only authority for user-facing Application Updates.
_Avoid_: OpenWorker release feed, source upstream, marketplace update

**Product Version**:
The version identity owned by Vegapunk for one Native Desktop Application release.
It is independent of OpenWorker's version sequence and is shared by the application metadata, release tag, update manifest, and signed artifacts.
_Avoid_: upstream version, inherited OpenWorker version, build-only version

**Anonymous Product Update**:
An Application Update retrieved from the Product Release Channel without requiring a user identity or account authentication.
Version 1 uses Anonymous Product Updates.
_Avoid_: authenticated updater, account-bound update, GitHub login

**Release Signing Authority**:
The protected Vegapunk release process that signs Stable Release artifacts for the Product Release Channel.
It is not available to Development Builds or ordinary local development machines.
_Avoid_: developer signing key, OpenWorker signing authority, unsigned release

**Stable Release Channel**:
The first-version Application Update stream containing Vegapunk releases approved for general user installation.
It excludes Development Builds and any future preview stream.
_Avoid_: development build, preview release, OpenWorker release

**Explicit Update Acceptance**:
The user's deliberate authorization to download and install an offered Application Update.
Automatic version checking does not constitute Explicit Update Acceptance.
_Avoid_: background download, automatic installation, passive update check

**Release Rollback**:
The maintainer-controlled recovery action that removes a faulty Stable Release from availability and restores a previously verified release as the recovery target.
It never silently downgrades an installed Native Desktop Application.
_Avoid_: automatic downgrade, source rollback, OpenWorker sync rollback

**OpenWorker Source Upstream**:
The external OpenWorker project whose source is manually reviewed as an input to Vegapunk development.
It is not an Application Update source and is never queried by the Native Desktop Application.
_Avoid_: user update channel, Vegapunk release channel, automatic upstream sync

**Development Build**:
A local or internal build used to develop Vegapunk and inspect changes before release.
It does not automatically check for or install Application Updates; only explicitly designated release or preview builds may connect to the Product Release Channel.
_Avoid_: production build, user release, auto-updating development app

**App Language Preference**:
The Native Desktop Application's single shared interface-language decision.
The current Desktop surface has no language switch, so integrated modules use the same current Desktop language and do not persist or expose a module-level language preference.
It affects static application GUI text only and never translates runtime logs, model output, user content, or third-party responses.
_Avoid_: model locale, server language, content translation

**Desktop Visual Baseline**:
The 1440 CSS-pixel-wide Native Desktop Application window used to compose the application's primary visual hierarchy, whitespace, and research texture.
The application remains functionally complete at 1024 CSS pixels without a separate compact visual system, while narrower windows receive only basic overflow protection.
_Avoid_: mobile-first composition, native-window assumption, false 1024px parity

**Application Module**:
A top-level capability area selected from the Native Desktop Application's module rail, such as Paper Tools, Skill Management, or System Settings.
Each Application Module owns its central work area while the module rail remains stable.
_Avoid_: role-specific console, page chrome, artifact preview

**Paper Tools**:
A Native Desktop Application module selected for finding and later working with scholarly papers.
Its Version 1 surface contains the Paper Search, Paper Deep Reading, and Citation Verification Paper Tool Submodules.
All three Version 1 submodules are visible placeholders until a stable paper-service design is selected.
_Avoid_: paper artifact preview, literature source, research project

**Paper Tool Submodule**:
One of the three child capability areas within Paper Tools.
Paper Tool Submodules use the Paper Tools' internal tab navigation and are not separate Application Modules or rail destinations.
_Avoid_: independent application, independent route, separate rail destination

**Paper Search**:
The visible but nonfunctional Paper Tool Submodule reserved for future research-question submission and literature reporting.
Its initial dialogue surface accepts no question and sends no external request.
_Avoid_: Elicit Paper Search record list, Elicit web Research Agent conversation, active search flow, Paper Deep Reading, Citation Verification

**Paper Search Mode**:
The future choice between different research depths within Paper Search.
Paper Search Mode is not surfaced in the initial placeholder interface.
_Avoid_: active search control, hidden future mode, streamed-answer promise

**Paper Research Question**:
A future natural-language question submitted through Paper Search to commission a Paper Research Report.
It is not accepted or persisted by the initial placeholder interface.
_Avoid_: Elicit web Research Agent follow-up, active chat thread, research task

**Paper Research Report**:
A future asynchronous, cited literature report created from a Paper Research Question after a stable source and report-generation design is selected.
It is not present in the initial placeholder interface.
_Avoid_: Elicit Paper Search record list, Deep Research Run, streamed chat answer

**Paper Deep Reading**:
A visible but nonfunctional Paper Tool Submodule reserved for future close reading of a selected paper.
It does not fetch, summarize, or open papers in the initial release.
_Avoid_: Paper Search, PDF reader, Paper Result Card interaction

**Citation Verification**:
A visible but nonfunctional Paper Tool Submodule reserved for future checking of citation claims and references.
It does not validate, modify, or persist citation information in the initial release.
_Avoid_: Paper Search, bibliography export, citation database

**High-Interest Papers**:
The domain-specific paper display section within Paper Tools, visually headed as “高热论文”.
It is distinct from Paper Search and initially shows noninteractive placeholder High-Interest Paper Cards.
_Avoid_: Paper Search results, saved library, paper detail page

**High-Interest Paper Card**:
A noninteractive placeholder card in High-Interest Papers.
It is unrelated to the still-undecided presentation of Elicit Paper Search results and does not promise an external paper source until the later daily-feed effort supplies one.
_Avoid_: Elicit Paper Search result presentation, external paper source, saved paper

**High-Interest Paper Domain**:
One fixed thematic filter applied only to High-Interest Papers.
The initial domain set is All Fields, AI Scientist, Seawater Desalination, Gas Turbines, Reverse Osmosis, and Embodied Intelligence.
_Avoid_: Elicit search constraint, arbitrary user-created tag, source database, research task

**Daily Research Brief Domain**:
A Sole Researcher-authored natural-language research topic that defines one Daily Research Brief subscription.
Version 1 has no fixed taxonomy; the topic's original text is its canonical meaning, without user-managed aliases, tags, or automatic rewriting.
_Avoid_: High-Interest Paper Domain, fixed taxonomy, arbitrary tag, generated search query

**Researcher Skill**:
A reusable Skill created and owned by the Sole Researcher through the Skill Management Application Module inside Harness.
_Avoid_: system Prompt, built-in Prompt, internal orchestration Prompt

**Local Skill**:
A Skill definition discovered on the Sole Researcher's machine from any configured local Skill Source, regardless of the AI tool, filesystem scope, or ownership path that exposes it.
It is the broad inventory term for the Skill Management module and includes Researcher Skills without being limited to them.
_Avoid_: curated Skill catalog entry, system Prompt, single-tool Skill

**Local Skill Source**:
A filesystem root, tool-specific directory, user-owned shared directory, or managed link location from which Local Skills are discovered or to which they are projected.
It may be user-scoped, tool-scoped, shared, or upstream-managed, and no single central directory is authoritative for every Local Skill.
_Avoid_: one fixed Skill directory, remote marketplace, runtime Prompt source

**Native Tool Project Skill Boundary**:
A project-level Skill directory that a Tool may continue to read and invoke through its own native behavior, but that Skill Management does not discover, display, bind, project, or modify in Version 1.
It is outside the manager's Skill identity, Tool applicability, and Apply state.
_Avoid_: ProjectBinding, active project context, managed project Skill

**Skill Source Package**:
A stable provenance identity for a coherent set of Local Skills obtained from one external or local source package.
Repeated downloads, updates, or partial reimports of the same package keep the same identity; download batches, versions, and local directories are metadata rather than separate packages.
_Avoid_: download batch, local source root, Skill Tool Target

**Anonymous Skill Management**:
The local-first Skill Management experience available to the Sole Researcher without sign-in, registration, profile, or account state.
Its inspection, projection, favorites, tags, and local organization operate from local application state rather than a Skill Management identity.
Version 1 does not include a remote Marketplace or community account surface.
_Avoid_: Skills Manager account, remote Skill identity, cloud-owned Skill profile, Skill marketplace client

**Local Skill Management Boundary**:
The boundary containing only the operations needed to inspect, organize, transfer, assess, and project Skills on the local machine, without directly editing Skill content or deleting Skill Bodies.
Remote catalogs, account services, community interaction, product-support submission, and any Skill Update lifecycle are outside this boundary.
_Avoid_: full Skills Manager product, Skill marketplace, remote Skill platform

**Non-destructive Skill Management Scope**:
The current Skill Management scope that discovers, inspects, explains, and may project Local Skills to configured Tools without directly editing Skill content or deleting Skill Bodies.
An explicit projection operation may create or remove a Tool symlink, but it never edits or deletes the resolved Skill Body.
Evidence-backed Manual Removal Commands may be displayed as advisory text, but Skill Management never executes them or interprets copying them as deletion intent.
_Avoid_: content editor, Skill uninstaller, central Skill owner

**Manager-owned Skill Metadata**:
Local Skill Management data such as favorites, tags, ordering, and private notes that changes only the manager's presentation and organization.
It never writes to a Skill Body, Tool Skill Target, symlink target, or external installer source.
_Avoid_: Skill frontmatter, source content, Tool installation state

**External Skill Acquisition Boundary**:
The boundary that leaves Skill installation, download, import, copying, and moving to npx, curl, git, or Tool-native workflows.
Skill Management also does not create new Skill Bodies or body-less placeholder Skills; it discovers resulting local bodies and manages only their inventory, explanation, metadata, and explicit Tool projections.
_Avoid_: Skill Manager installer, central import hub, hidden file migration

**Single-Tool Projection Action**:
An explicit Apply or On -> Off operation targeting exactly one configured Tool Skill Target.
Skill Management does not expose a batch projection action that changes multiple Tool paths as one user operation.
_Avoid_: apply all, disable all, bulk synchronization

**Skill Body Reveal Action**:
A read-only action that opens a verified Skill Body or installation path in Finder for local inspection.
It does not edit, delete, move, or otherwise mutate the Skill Body or Tool Skill Target.
The card-level action reveals the resolved Skill Body, while a Tool-level action reveals that Tool's installation entry; the precise interaction design is deferred to a later prototype.
_Avoid_: external editor, file operation, automatic cleanup

**Unavailable Skill Tool**:
A configured or recognized Tool Skill Target whose Tool is not installed or whose Skill root cannot be used.
It is distinct from an available Tool with a missing Skill (`Off`) and does not expose an Apply action.
_Avoid_: Off Skill, broken Skill projection, callable Tool

**Shared Skill Analysis Provider**:
The previously considered Desktop App model provider for Skill translation and risk analysis.
It is deferred outside the current Skill Management scope and is not required for discovery, inspection, metadata, or projection.
_Avoid_: current V1 dependency, Skill Manager LLM account, Marketplace provider

**Transient Skill Analysis Result**:
A deferred AI analysis result that is not part of the current Skill Management scope.
If analysis returns in a later module, its persistence policy requires a new decision.
_Avoid_: current Skill fact, authoritative risk state, automatic metadata

**Installed Local Skill**:
A Skill directory already present on the local machine, including one previously installed from a remote catalog or restored from an older cloud-oriented format.
Removing remote features never removes its files or local tool projections; only obsolete remote metadata and actions are discarded.
_Avoid_: Marketplace-owned Skill, cloud Skill, disposable install artifact

**Local Tool Synchronization**:
The local filesystem operation that observes and, after an explicit user action, updates the relationship between Local Skills and configured Skill Tool Targets.
It does not require a central Skill directory, upload Skill content, or require a cloud identity.
_Avoid_: cloud sync, cross-device synchronization, account sync

**Cloud Skill Synchronization**:
A deferred cross-device capability that would upload Skill metadata or content to a remote service and reconcile it across installations.
Version 1 does not expose or persist Cloud Skill Synchronization; local import/export is the supported portable transfer mechanism.
_Avoid_: Local Tool Synchronization, save-time linking, Marketplace refresh

**Local Skill Usage Monitor**:
The historical on-device collection of Skill invocation counts and recency from configured tool hooks.
It is outside the current Skill Management scope; the manager does not install or manage those hooks and does not collect or display Skill usage history.
_Avoid_: product telemetry, cloud analytics, account activity, current V1 capability

**Desktop Product Telemetry**:
An optional application-wide collection of anonymous product-usage events managed by the Native Desktop Application's privacy boundary.
Skill Management does not own its consent, storage, initialization, or transport.
_Avoid_: Local Skill Usage Monitor, Skill invocation history, Skill account

**OpenWorker Global Theme Contract**:
The shared visual theme contract applied by the Native Desktop Application and its Application Modules through the application theme state and common surface tokens.
Application Modules inherit this contract, including the shared font stack, instead of maintaining an isolated theme root, font override, or competing background palette.
_Avoid_: Skills Manager theme, module-local dark mode, independent surface palette

**Skill Tool Target**:
One product-supported AI coding assistant represented by the fixed Version 1 Skill Tool Set, whether or not it is currently installed or available on the machine.
Its one or more native Skill roots can be discovered, inspected, enabled, disabled, or projected by Skill Management when the corresponding adapter is available.
Multiple native roots remain one Tool Target in the UI and metadata; their concrete paths and provenance are retained as installation details.
_Avoid_: model provider, research agent, independent application

**Tool Skill Root**:
One concrete native filesystem root through which a Skill Tool Target discovers Skills, such as a user, shared, or fallback Skill directory.
It is an installation path within one Tool Target, not an additional Tool and not a central Skill Manager repository.
_Avoid_: separate Tool, central hub, arbitrary filesystem root

**Canonical Tool Projection Root**:
The one Tool Skill Root declared by a Tool adapter as the default target for an explicit Apply action.
If this root does not exist, an explicit Apply may create the directory and then create or repair the symlink under it; Refresh never creates it implicitly.
Apply changes only this root's directory entry and symlink; other user, shared, or fallback roots remain discovery and inspection sources unless a later decision explicitly gives them a projection action.
It is an adapter fact, not a hidden global/project context and not a user-selectable Custom Tool path.
_Avoid_: implicit active project, all-roots Apply, central Skill Manager directory

**Predefined Skill Tool Set**:
The fixed Version 1 allowlist of five Skill Tool Targets supported by Skill Management.
The allowlist is product-defined rather than inferred from every detected CLI, and it does not expose Custom Tool registration or Custom Tool CRUD.
The allowlist replaces the former Antigravity entry with Kimi Code.
_Avoid_: arbitrary tool registry, detected-CLI catalog, Custom Tool surface

**Kimi Code**:
The Version 1 predefined Skill Tool Target that replaces Antigravity in the Predefined Skill Tool Set.
Its canonical Tool ID is `kimi-code`, its user-facing name is `Kimi Code`, and its native CLI command is `kimi`.
Its identity is distinct from the generic Kimi model/provider name; its native configuration and Skill paths are adapter facts and are not inherited from Antigravity.
Its Canonical Tool Projection Root is `~/.kimi-code/skills/`; `.agents/skills/` is a shared discovery root, while Kimi Code project roots belong to the Native Tool Project Skill Boundary.
_Avoid_: Antigravity, Kimi model provider, Custom Skill Tool

**Custom Skill Tool**:
A user-defined Tool integration registered with an arbitrary name, command, or Skill path.
Custom Skill Tools are outside the Version 1 Skill Management boundary, so the UI provides no create, edit, delete, or arbitrary registration operation for them.
_Avoid_: Predefined Skill Tool Set, discovered Tool, Tool Skill Installation

**Callable Skill Tool**:
A Skill Tool Target whose installation path currently contains readable content for a Local Skill, so that the tool can invoke that Skill.
It is an observed availability fact, not a list of every Tool supported by Skill Management.
_Avoid_: supported Tool, enabled boolean, configured but empty Tool

**Tool Skill Applicability**:
The On or Off fact for one Skill at one Tool Skill Target.
It is On when any usable Tool Skill Root contains readable Skill content through either a real directory or a valid symlink, and Off when no root contains such content.
Root-level materialization, path, and provenance remain visible in the Skill details even when the Tool row presents one aggregate applicability state.
When at least one root is a Body-Hosting Root, the aggregate Tool state is green On and its switch is disabled even if another root contains a valid symlink projection.
When no Body-Hosting Root exists but one or more roots contain valid symlink projections, the aggregate Tool state is yellow On and its switch is enabled; On -> Off removes every valid symlink projection for that Skill under that Tool atomically, without touching the Skill Body.
If a yellow On Tool also has broken symlink roots, those roots remain visible as errors and the same On -> Off action removes all valid and broken symlink entries for that Skill under that Tool atomically.
_Avoid_: linked state, installation form, manager ownership

**Mixed Tool Skill State**:
A Tool Skill Target whose roots contain both a real Skill Body and one or more valid symlink projections for the same Skill.
It is presented as the Body-Hosting case at the aggregate Tool row: green On with a disabled switch, while the symlink roots remain visible in the detail view.
The aggregate On -> Off action does not remove those symlinks because the Tool is already applicable through its real Skill Body.
_Avoid_: partially Off Tool, duplicate Tool row, automatic symlink cleanup

**Body-Hosting Tool**:
A Skill Tool Target whose path contains the Skill Body directly as a real directory rather than through a symlink projection.
Its Tool Skill Applicability is On, but its per-Tool switch is disabled because turning it Off would require deleting the Skill Body rather than removing a projection.
_Avoid_: source toggle, enabled link, editable switch

**Symlink Projection Tool**:
A Skill Tool Target with one or more valid symlink projections to a Skill Body elsewhere and no Body-Hosting Root for that Skill.
Its per-Tool switch may remove or restore all of that Tool's symlink projections for the Skill as one atomic Tool-level action without deleting the Skill Body.
_Avoid_: Skill Body owner, central Tool, delete Skill

**Tool Skill Installation**:
A Skill directory or symlink that exists under a Skill Tool Target and can be called by that tool.
Its availability is determined by the target's readable content, while its materialization form remains a separate fact from whether the Skill is applicable to the tool.
_Avoid_: central Skill copy, managed link, enabled boolean

**Tool Skill Path Collision**:
An Apply attempt whose target path is already occupied by a real Skill with different content.
It is a path conflict rather than a Skill identity conflict; Apply fails without overwriting, renaming, or moving the existing Skill.
_Avoid_: merged Skill, deletion ambiguity, automatic replacement

**Broken Skill Projection**:
A Skill Tool Installation path that is a symlink whose target cannot be resolved to readable Skill content.
It is Off/Error during read-only discovery when no other root makes the Tool applicable.
If another root provides a valid projection, the aggregate Tool remains yellow On while this root is shown as an error detail.
An explicit Apply may replace the dangling symlink with a projection to the selected Skill Body, and an explicit On -> Off for a yellow Tool removes the broken entry together with the Tool's other symlink entries.
_Avoid_: callable Skill, valid projection, implicit repair

**Skill Identity**:
The logical grouping of Tool Skill Installations whose declared identity and complete readable content represent the same Skill.
Matching directory names alone do not establish identity; installations with divergent content are separate Skill variants and are never included in one another's edit or deletion set.
_Avoid_: folder name, central copy, enabled state

**Skill Body**:
The resolved readable directory containing the actual content of a Skill Installation.
For a symlink installation, the Skill Body is its resolved target, and it does not have to live in a central Skill Manager directory.
_Avoid_: hub directory, link entry, display card

**Unprojected Skill Body**:
A known readable Skill Body that currently has neither a Body-Hosting Tool nor a valid symlink projection under the configured Tool Skill Targets.
It remains in Skill Management's inventory with no callable Tool metadata and all known Tools Off.
_Avoid_: deleted Skill, missing body, unavailable source

**Synchronized Skill Replica Set**:
The Tool Skill Installations grouped under one Skill Identity because their complete content agrees.
An edit to the Skill Body propagates to every equivalent replica, while a shared symlink target is written only once.
_Avoid_: independent copies, enabled tools, central mirror

**Synchronized Skill Edit Transaction**:
A single all-or-nothing content edit applied to every equivalent Skill Body or replica in one Synchronized Skill Replica Set.
If any target cannot be written, the edit fails as a whole and no partial content change is accepted.
_Avoid_: best-effort fan-out, partial save, divergent write result

**Synchronized Skill Deletion Transaction**:
A single all-or-nothing deletion of a Skill Body replica set and its related symlink entries.
The deletion set is limited to verified Skill Body replicas and symlink entries under configured Tool Skill Targets.
If Skill Management cannot complete that verified deletion set, it fails the operation rather than intentionally accepting a partial deletion; external symlinks outside those targets are not automatically searched for or deleted.
_Avoid_: best-effort cleanup, partial uninstall, orphaned deletion state

**Symlink Provenance**:
The evidence-based explanation of a symlink's target and known management source, such as npx skills, Skill Management, a Tool-native installer, or an unknown origin.
It must not claim who created a historical link when no registry or source metadata proves that fact.
_Avoid_: guessed creator, installation form, ownership inferred from color

**Installation Provenance**:
The evidence-backed record of how a Tool Skill Installation entered the machine, including its installer or source, scope, and an appropriate removal route when one is known.
It determines the recommended deletion command but does not make a historical creator claim without supporting metadata, and a later rescan may invalidate stale provenance.
Known external provenance does not lock the editor: the Sole Researcher may edit the actual Skill Body, with a warning that the installer or Tool may overwrite local changes later.
_Avoid_: filesystem guess, symlink target alone, generic rm as universal uninstall

**Manual Removal Command**:
A copyable installer-specific or filesystem cleanup command that Skill Management recommends for a Local Skill.
It is advisory display text only: copying it does not express deletion intent, create a pending state, or change Skill Management state; the Sole Researcher may run it manually at any time.
_Avoid_: automatic shell execution, hidden uninstall, generic command without a known target

**AGENTS.md Application Module**:
A top-level Application Module in the Native Desktop Application for discovering, inspecting, and editing durable `AGENTS.md` instruction sources.
It is selected from the Harness Sidebar group alongside Skill Management and does not treat instruction files as Skills or application settings.
_Avoid_: Settings subsection, Skill card, Prompt Library

**Harness**:
A top-level Sidebar navigation group for the local coding-agent infrastructure surfaces.
It contains Skill Management and the `AGENTS.md` Application Module as sibling destinations, but it does not own a separate content surface of its own.
_Avoid_: standalone Harness page, model provider group, generic application settings

**Artifact Preview**:
The contextual right-side area of the Native Desktop Application that appears when a selected non-PDF artifact has a previewable representation.
It remains absent when no artifact is selected and does not replace the central work area.
_Avoid_: Browser PDF Reader, full-screen reader, artifact explorer, permanent third column

**Browser PDF Reader**:
The browser-native PDF viewer opened in a new tab for every user-visible PDF artifact.
It replaces all PDF uses of Artifact Preview and embedded artifact viewing.
Browser configuration determines the reader implementation and whether a user downloads the file instead.
It is reached through a dedicated PDF action rather than the Artifact Explorer sidebar.
_Avoid_: system-default desktop PDF app, side-panel PDF preview, embedded PDF iframe

**Research Identity Layer**:
The visual expression of Vegapunk's computational-research identity through generated structures, particle fields, ASCII treatments, or scientific diagrams.
It must be clearly perceptible at the Desktop Visual Baseline in durable content-bearing and exhibition-oriented contexts, while never competing with controls, forms, dense records, or other high-frequency work.
It appears only when it clarifies interface state, hierarchy, or a Durable Content Anchor.
_Avoid_: imperceptible background noise, uncropped decorative wallpaper, placeholder decoration, fake data visualization, visual noise

**Durable Content Anchor**:
A product area, research object, artifact, or stable placeholder whose information architecture is intended to persist as its content develops.
Research Identity Layers and Material Expression Layers may attach to Durable Content Anchors, including a placeholder with a clear continuing product owner, so visual-system work survives feature development.
_Avoid_: invalid elements scheduled for deletion, decorative treatment with no persistent product owner, a one-off temporary scaffold

**Deterministic Identity Graphic**:
A non-data-bearing visual generated from a stable module or project identity, so the same object receives the same computational graphic on later visits.
It expresses research character without claiming to visualize a model state, research result, evidence relation, or runtime metric.
_Avoid_: simulated telemetry, fake neural-network diagram, unlabelled data visualization

**Rice-White Surface**:
The Native Desktop Application visual foundation of warm rice-white surfaces, graphite text, restrained rules, and a Unified Tonal Spectrum for non-error interface signals.
Navigation belongs to the same continuous light field as the work area rather than becoming a dominant dark rail.
Local Material Expression Layers may enrich this foundation without replacing it with a persistent dark theme.
_Avoid_: dark dashboard shell, stark cool-white surface, a separate blue identity spectrum, competing semantic accent colors

**Material Expression Layer**:
A localized visual layer above the Rice-White Surface that applies a selected craft or art material vocabulary to frame research identity, object focus, or exhibition-oriented content.
It remains subordinate to text, controls, real charts, and explicit state indicators, and never substitutes for a real research measurement or lifecycle state.
_Avoid_: global recoloring, decorative wallpaper, implicit data visualization, themed controls on every surface

**Maki-e Research Expression**:
The only directly recognizable Material Expression Layer in the initial visual system.
It draws on Maki-e's material precision, controlled powder-like aggregation, and compositional restraint rather than reproducing historical motifs.
Other art forms may inform its whitespace, asymmetry, or texture principles, but may not appear as independently recognizable visual languages.
_Avoid_: Japanese-style collage, literal traditional motifs, a second named art direction

**Exhibition Module**:
A Native Desktop Application module whose primary job is to frame research context, progress, or outputs rather than support dense configuration work.
The Exhibition Module uses a stronger distributed Research Identity Layer in its title, structural whitespace, and current-object states while operational modules remain visually quiet.
_Avoid_: a poster treatment on every module, standalone decorative field, decorative configuration form

**Research Editorial Typography**:
The three-role type system of a compact, hard-edged Neo Swiss grotesk for display hierarchy, a highly legible sans-serif for prose and controls, and a mono face for machine-readable identifiers.
The display role creates research-publication authority without weakening Chinese text readability or operational density.
_Avoid_: rounded display type, decorative serif headline, one font for every hierarchy

**Unified Tonal Spectrum**:
The low-saturation aged-gold or tea-gold visual-identity tone used across active interface signals and Deterministic Identity Graphics.
Its sense of depth comes from controlled changes in lightness, opacity, particle density, texture, and reflectance rather than from introducing multiple decorative hues.
Dedicated error and warning colors retain their semantic purpose.
_Avoid_: rainbow particle art, a separate blue identity spectrum, multiple competing brand accents, an identity tone used as an error state

**Calm Computational Motion**:
The motion discipline for Deterministic Identity Graphics and the Occluded Point-Cloud Substrate: static by default, with one low-amplitude 180 to 220 ms response only on a module change, selection of a real research object, or start of a real operation.
It excludes indefinite decorative loops, operational-surface motion, and motion that ignores the system reduced-motion preference.
_Avoid_: animated wallpaper, perpetual particle drift, distracting form animation

**Point-Cloud Grammar**:
The primary Research Identity Layer visual language of Unified Tonal Spectrum particles arranged by density, flow, and occasional sparse links.
ASCII characters and halftone dots are close-range supporting textures, while literal neural-network diagrams and generative terrain are excluded from the product identity.
_Avoid_: style-sample collage, fake model topology, generic AI landscape

**State Particle Field**:
A non-data-bearing arrangement of particles whose density, grouping, and contrast express interface hierarchy or interaction state such as inactive, selected, focused, or currently running.
It does not quantify runtime progress, research evidence, model structure, or any other scientific result.
_Avoid_: decorative wallpaper, telemetry substitute, unlabeled data chart

**Occluded Point-Cloud Substrate**:
The persistent, static, and clearly perceptible Unified Tonal Spectrum point-cloud composition anchored to the lower-right of the Native Desktop Application's main content background.
Its subject is a non-figurative directional abstract formation, not a portrait, neural-network diagram, star field, or implicit data visualization.
Foreground panels, records, and content naturally crop and occlude it, so it remains a single shared research-identity subject without competing with reading or controls.
_Avoid_: random redraws, full-bleed particle wallpaper, overlap with text or inputs, a generic star field

**Stable Particle Identity**:
The deterministic particle distribution assigned to one Application Module or research object.
It remains unchanged while that object is viewed and may make one brief transition when the active module or object changes, but never continuously drifts or reshuffles.
_Avoid_: random redraw on render, perpetual particle animation, state ambiguity

**Particle State Trigger**:
The limited interaction set that may strengthen a State Particle Field: current navigation or selected content, direct input focus, and a real in-progress operation.
Static list items, ordinary cards, and destructive controls remain free of particle emphasis.
_Avoid_: particle on every component, decorative busywork, simulated progress

**Research Texture Set**:
The controlled visual vocabulary of particles as the primary material, fine grids and crop marks as structural precision, and local halftone as a close-range texture.
It excludes unlabeled chart-like curves and large ASCII backgrounds because they imply unsupported data or compete with research content.
_Avoid_: fake plot line, ASCII wallpaper, competing decorative language

**Particle Identity Hierarchy**:
The rule that all interface elements share the Research Texture Set while only Application Modules, research objects, workflow groups, and the current record receive their own Stable Particle Identity.
Individual static cards and parameter rows use common local texture rather than independent visual signatures.
_Avoid_: one illustration per card, record-level visual clutter, noisy catalogue

**Particle Semantic Boundary**:
The prohibition on using particle count, density, or motion as an implicit representation of quantities, completion, research progress, or scientific results.
Particles express identity, interface hierarchy, and permitted interaction states only; real information remains explicit text, controls, charts, or labelled visualizations.
_Avoid_: atmospheric progress indicator, ambiguous quantitative texture, decorative telemetry

**Particle Intensity Gradient**:
The allocation of particle emphasis by Application Module: low in System Settings and Prompt Library, medium in Conversations and Skill Management, and high in the Exhibition Module.
The gradient keeps frequent configuration work quiet while giving research-context views a stronger, still non-data-bearing identity.
_Avoid_: uniform decoration, expressive configuration form, silent operational surface

**Grid-Aware Particle Distribution**:
The visual rule that particle positions vary irregularly in size, spacing, density, and blank space while tending to collect near established layout lines, headings, divisions, crop marks, and grid intersections.
It creates a computational-paper texture that is neither a random star field nor a chart-like line drawing.
_Avoid_: uniform particle wallpaper, cosmic motif, decorative wave path

**Exhibition Field**:
A distributed grid-aligned visual field across an Exhibition Module's content surfaces, whitespace, and active-object boundaries.
It gives the Research Identity Layer the same compositional status as title, status, and research metadata without reserving a standalone decorative panel.
_Avoid_: visual-effect card, framed AI demo, dedicated particle canvas

**Explicit Grid**:
The selectively visible fine-line layout structure used in editorial focal areas such as an Exhibition Field.
It supports composition and alignment without becoming a universal page background or a substitute for meaningful interface hierarchy.
_Avoid_: graph-paper wallpaper, decorative grid everywhere, fake data visualization

**Deep Research Run**:
A bounded investigation of one research question that gathers evidence and produces a cited report without entering the Discovery experiment loop or Paper Handoff.
A stopped, interrupted, or failed Deep Research Run is repeated only by creating a new Run because it has no resumable Workflow Progress checkpoints.
_Avoid_: QA session, Discovery Launch, chat

**Research Submission**:
The goal, domain, constraints, reference materials, datasets, and optional baseline code supplied by the Sole Researcher to start a Discovery Launch.
It remains distinct from generated artifacts and the Paper Input Bundle.
_Avoid_: Task Authoring Form, Paper Input Bundle, Launch filesystem

**Staged Research Upload**:
A temporary input file stored before one Deep Research Run claims it during creation.
It may be claimed once, while an unclaimed upload expires; it is neither a reusable file library nor a research artifact.
The Native Desktop Discovery Module uses Discovery Preparation source files instead.
_Avoid_: Discovery Preparation source file, attachment library, permanent upload, research artifact, shared input

**Unstructured Discovery Source**:
The arbitrary plain text and files that the Sole Researcher supplies to prepare a Discovery Launch.
It requires no prescribed schema or complete research-task structure before the model-assisted conversion step.
Its Version 1 accepted file types are plain text, Markdown, PDF, DOCX, CSV, and ZIP baseline-code packages.
Other file types are rejected explicitly before conversion.
Conversion cannot begin while any included accepted source fails validation or text extraction.
The failed source remains visible in the Discovery Preparation with an explicit reason, and no partial conversion is produced from the remaining sources.
_Avoid_: Task Authoring Form, structured Research Submission, required intake template

**Formatted Discovery Input**:
The editable Discovery-ready content generated from an Unstructured Discovery Source by the model-assisted conversion step.
The Sole Researcher can inspect, revise, and explicitly save a revision in the Native Desktop Discovery Module before starting the Discovery Launch.
_Avoid_: raw source material, automatically launched task, immutable model output

**Discovery Preparation**:
A reusable Discovery Preparation record that owns Unstructured Discovery Source files and saved Formatted Discovery Input revisions.
It remains available after a Discovery Launch starts and can create multiple new Launches.
Each Launch captures the explicitly selected input revision and source files in its own immutable start-time record.
_Avoid_: one-time Staged Research Upload, mutable Launch input, current-run-only form

**Researcher Tool Prompt**:
A named instruction maintained by the Sole Researcher in System Settings for an explicitly invoked model-assisted tool operation.
Researcher Tool Prompts are kept together in their own settings area, separate from the system Prompt Library and Researcher Skills.
_Avoid_: Registered Prompt, system orchestration prompt, Researcher Skill

**Discovery Input Conversion Prompt**:
The Researcher Tool Prompt that instructs a model to convert an Unstructured Discovery Source into Formatted Discovery Input.
_Avoid_: Discovery generation system prompt, Task Authoring Form, direct launch command

**Discovery Input Conversion Invocation**:
One explicit model call that applies the Discovery Input Conversion Prompt to an Unstructured Discovery Source.
It resolves the current System Settings default text model and parameters when invoked and offers no Discovery Module-local model override.
_Avoid_: Discovery-local model picker, system orchestration prompt, automatic background conversion

**Native Desktop Prompt Library Module**:
The OpenWorker System Settings module that exposes Vegapunk's core Prompt Library capabilities: browse, search, inspect, edit, validate, and save Registered Prompts.
Version 1 excludes Chinese Prompt Mirrors, automatic translation, batch synchronization, creation, deletion, renaming, and metadata editing.
_Avoid_: App Language Preference, Prompt translation tool, user-created Prompt collection, Researcher Skill

**Prompt Library**:
The single service-wide collection of every editable system Prompt text, stored as repository source files and including scientific-behavior prompts and infrastructure/scaffolding prompts.
Each new Deep Research Run or Discovery Launch reads it when it starts; edits affect work that starts afterwards and never change work already running.
There are no per-Launch prompt overrides.
Saved Prompt revisions do not retain intermediate user history; each Registered Prompt retains only its current active body and its current-version System-Original Prompt.
_Avoid_: per-Launch prompt snapshot, mid-run prompt edit, hardcoded prompt, curated prompt subset

**Registered Prompt**:
A Prompt Library entry with a stable identity and runtime call site supplied by the installed Vegapunk version.
The Sole Researcher may revise its content but cannot edit its system-maintained metadata or create, delete, or rename Registered Prompts through System Settings.
_Avoid_: ad hoc Prompt, user-created Prompt, unregistered Prompt

**System-Original Prompt**:
The default body for one Registered Prompt supplied by the currently installed Vegapunk version.
It is retained separately from the Sole Researcher's active body so the editor can load that one Prompt's current-version default into a Pending Prompt Revision; no intermediate user revision history is retained.
_Avoid_: first-ever Prompt body, immutable migration baseline, user revision history

**Pending Prompt Revision**:
An unsaved proposed body for one Registered Prompt that has no effect until an explicit save passes the Prompt Template Contract and atomically replaces the Prompt's repository source file.
_Avoid_: autosaved Prompt, Prompt Override, partially saved Prompt

**Prompt Orchestration Position**:
The workflow, stage, and group-local first-call position at which a Prompt participates in orchestration, together with whether its use is conditional, repeated, or mutually exclusive.
It is declared explicitly in the system-maintained Prompt catalog rather than inferred from runtime code.
Prompt Orchestration Positions never imply one global linear order across independent workflows.
_Avoid_: global Prompt order, alphabetical execution order, card order

**Prompt Template Contract**:
The declared required and allowed interpolation variables plus structural validity rules that every Prompt revision must satisfy before entering the Prompt Library.
It rejects empty or malformed Prompt revisions before a research Run can consume them.
_Avoid_: runtime-only Prompt validation, undeclared template variable, best-effort save

**Run Parameter Registry**:
The service-wide catalog of every run parameter and its default, description, type, and validation rule, managed through Native Desktop Settings and the local sidecar.
Only intentionally configurable parameters with stable identities belong to the Registry; secrets, internal paths, protocol details, and implementation constants do not.
An allowlisted subset may be supplied as Researcher Run Settings without changing the Registry defaults.
_Avoid_: raw config file editing, unrestricted researcher override, mid-run change, undocumented parameter

**Settings Activation Boundary**:
The start of the next new Deep Research Run or Discovery Launch, when committed System Settings changes become effective without requiring a service restart.
Work already running retains the settings resolved at its own start, while a newly admitted Discovery Launch uses the latest committed settings.
A Launch Resume continues to use its original Launch Configuration Snapshot.
_Avoid_: mid-run settings update, service-restart activation, immediate field activation

**Default Configuration Revision**:
One server-validated, atomic version of the three root model bindings and all Run Parameter Registry defaults produced by a successful System Settings save.
A new research Run captures exactly one complete Revision, while an invalid change leaves the preceding Revision unchanged.
_Avoid_: partial parameter save, field-by-field activation, mixed configuration version

**Configuration Readiness**:
The derived indication of whether a structurally valid Default Configuration Revision currently has the Provider Connections required to start research work.
An unready Revision may be saved, but Capability Preflight blocks execution until its dependencies validate successfully.
_Avoid_: save validity, silent Provider fallback, permanently cached connection status

**Researcher Run Setting**:
An allowlisted execution choice the Sole Researcher supplies when creating one Deep Research Run or Discovery Launch, such as the Discovery loop-round limit.
It affects only that work and is captured with its effective configuration.
_Avoid_: Run Parameter Registry, global default, arbitrary config override, mid-run change

**Launch Configuration Snapshot**:
The complete copy of the Prompt Library and effective run parameters, including Researcher Run Settings, that a Discovery Launch captures into its own results directory at start.
The Launch and any Launch Resume read only this snapshot, and it is the authoritative record of the configuration behind that Launch's results.
_Avoid_: live global config, implicit defaults, post-hoc reconstruction

**Discovery Launch Admission**:
The product rule that accepts Moonshot only when no Discovery Launch is running.
An admitted Launch starts immediately, while another request is rejected rather than becoming queued work.
_Avoid_: Launch Queue, queued Launch, delayed Launch

**Graceful Stop**:
The default way to stop running research work: it finishes its current smallest unit, persists any supported checkpoint, and exits with the work marked stopped without triggering later stages.
A stopped Discovery Launch may resume, while a stopped Deep Research Run requires a new Run; force kill remains an Admin-only fallback.
_Avoid_: default hard kill, pause, wait-for-round-completion

**Interrupted Launch**:
A Discovery Launch whose execution ended without a trustworthy terminal outcome.
Its durable progress is reconciled first; if it did not complete, the Sole Researcher may explicitly resume it, but the product never resumes it automatically.
_Avoid_: failed Launch, aborted Launch, automatic resume

**Launch Resume**:
An explicit request to continue a stopped or reconciled-incomplete Interrupted Launch from its Workflow Progress checkpoints using exactly the prompts and parameters captured at its original start.
It is admitted only when no other Discovery Launch is running, preserves earlier Execution Attempts, adds a new attempt at the current milestone, and never absorbs later Prompt, model-binding, or run-parameter edits.
Each resumed Execution Attempt resolves the current Provider Connection for the originally bound Provider because credentials are never stored in the Launch Configuration Snapshot.
_Avoid_: new Launch, automatic resume, mixed-configuration continuation, edit absorption on resume

**Research Progress Timeline**:
The durable ordered chain of core milestones through which the product presents one Deep Research Run or Discovery Launch.
Milestone state changes are the product's persisted progress events, so live and reopened views share one record while detailed operational output remains in the Research Activity Stream.
_Avoid_: transient progress, raw internal trace, replacement for activity output

**Selected Launch Status Wheel**:
The manual-browsable visual presentation of one Selected Discovery Launch's durable, non-repeating Research Progress Timeline.
It centers the current state and keeps terminal exceptions explicit, while never filtering or controlling the Raw Discovery Console.
_Avoid_: global status dashboard, progress animation, raw-console filter

**Research Activity Stream**:
The bounded durable terminal-style sequence of curated and redacted operational messages for one Deep Research Run or Discovery Launch.
It complements the Research Progress Timeline, resumes after reconnect, may discard its oldest messages at the product limit, and never exposes raw Admin logs, hidden prompts, or internal reasoning.
_Avoid_: raw Admin log, internal trace, replacement for progress milestones

**Raw Discovery Console**:
The Native Desktop Discovery Module's terminal surface that renders a Discovery Launch's stdout and stderr in their original order without summarization, transformation, or redaction.
Its Version 1 scope is the Sole Researcher's private intranet deployment and may expose all process output, including credentials or hidden prompts.
Selecting a Launch or reconnecting replays its complete durable console history before following appended output.
Version 1 applies no display-line limit, replay cursor, or output-processing layer.
It is distinct from the curated Research Activity Stream and does not replace durable progress milestones.
_Avoid_: sanitized activity stream, interpreted progress view, production multi-user log viewer

**Execution Attempt**:
One contiguous execution of a Research Progress Timeline milestone.
A Discovery Launch Resume adds an attempt while preserving earlier attempts; an Execution Attempt is not an Experiment Run.
_Avoid_: Experiment Run, resumed Launch, overwritten attempt

**Live Launch View**:
The Native Desktop Discovery Module view that follows the currently running Discovery Launch in real time: its current stage and round, each runtime artifact as soon as it is persisted, and streaming key logs. It does not wait for stage or Launch completion.
_Avoid_: post-hoc report, final-artifact-only view, completed-Launch-only view

**Artifact Explorer**:
The Native Desktop Discovery Module's contextual right rail that exposes every non-PDF human-readable file a Launch persists as a browsable tree with content viewers, guaranteeing that all rail-eligible runtime information is reachable.
Markdown artifacts render as documents while other sidebar-eligible text, data, code, source, and image artifacts use direct human-readable viewers.
Structured views such as the Launch timeline and Experiment Run detail are navigational overlays on top of it, never the only path to sidebar-eligible artifact information.
In the Native Desktop Discovery Module, it is scoped to the Selected Discovery Launch and excludes PDF and machine-only binary runtime files from the tree.
_Avoid_: central-work-area artifact viewer, PDF right-rail preview, raw filesystem mirror, binary-file browser, final-only gallery, unmodeled human-readable information blind spot

**Discovery Launch Archive**:
The Native Desktop Discovery Module's chronological collection of every running or completed Discovery Launch.
Selecting one Launch makes its complete sidebar-eligible artifact tree available through the Artifact Explorer instead of limiting the researcher to the current Launch.
Its user-visible PDFs remain available through their dedicated Browser PDF Reader actions.
_Avoid_: current-run-only output, curated result gallery, discarded completed run

**Selected Discovery Launch**:
The one Discovery Launch selected from the Discovery Launch Archive as the Native Desktop Discovery Module's current viewing context.
Its selection simultaneously determines the Raw Discovery Console history in the central work area and Artifact Explorer tree in the right sidebar.
_Avoid_: independent console selection, independent artifact selection, multiple concurrent viewing contexts

**Curated Research Artifact**:
A stable product-visible output selected from one Deep Research Run or Discovery Launch and addressed by an opaque artifact identity rather than a filesystem path.
It excludes raw logs, hidden prompts, internal configuration, temporary files, and unrestricted workspace content.
_Avoid_: Artifact Explorer entry, arbitrary file path, raw runtime artifact

**Reproducibility Bundle**:
The sanitized downloadable package of code, effective non-secret settings, metrics, and instructions needed to reproduce a completed Discovery Launch's selected experimental result.
It is a Curated Research Artifact rather than a copy of the complete Launch workspace.
_Avoid_: full workspace archive, raw artifact dump, configuration snapshot

**Task Authoring Form**:
The Native Desktop Application form through which the researcher directly composes a research task's structured fields (system, task description, domain, background, constraints) and uploads its baseline code package. It performs no LLM assistance; a task without baseline code can only take the report path, not the experiment path.
_Avoid_: Task Builder, automatic task generation, topic-only quick start

**Task Builder**:
The planned later capability that turns a research topic plus uploaded reference materials into a draft task via model assistance, for researcher review before Launch Admission. It is not part of the first Native Desktop Application delivery.
_Avoid_: Task Authoring Form, fully automatic launch, current capability

**Discovery Launch**:
A bounded research effort that may contain multiple Discovery Rounds and Candidate Experiments. It may automatically produce at most one Paper after its configured Discovery work is complete; research intended to produce another Paper begins as a new Launch.
_Avoid_: session, round, candidate experiment

**Discovery Round**:
One iteration within a Discovery Launch in which research ideas are proposed and evaluated through the configured workflow.
_Avoid_: launch, session, experiment run

**Candidate Experiment**:
One research idea and its associated Experiment Runs within a Discovery Round.
_Avoid_: discovery round, experiment run, final paper

**Experiment Run**:
One independently reproducible attempt within a Candidate Experiment, with the exact inputs, implementation, execution record, outputs, and outcome used for that attempt.
_Avoid_: candidate experiment, discovery round, launch

**Model Provider**:
The configured source of model inference used by LLM-backed agent roles.
It does not own code-workspace operations or Candidate Experiment execution.
_Avoid_: model, coding agent CLI, Experiment Backend

**Relay Provider Module**:
The complete researcher-facing Model Provider entry for the Relay service.
It includes the provider identity, supported connection fields, connectivity verification, and selectable models needed to route real model calls through Relay after configuration.
Its model calls use the Relay model's declared Responses protocol so reasoning, tool use, structured output, and continuation semantics remain intact.
Its connection defaults to the project's current Relay deployment and may expose an explicitly supported Endpoint override as an advanced setting.
Its visual treatment follows the shared Model Provider gallery and Provider detail view used by the other providers; Relay does not introduce a drawer, split layout, or Relay-specific navigation model.
Its first text-model offering recommends `gpt-5.6-sol`, keeps image models outside this configuration surface, and permits the Sole Researcher to enter another explicit Relay model identity.
It is not a decorative provider card and does not create a second Relay identity alongside the project-wide `relay` Provider.
_Avoid_: Relay placeholder card, separate relay provider, display-only provider

**Unified Model Catalog**:
The single project-wide vocabulary for selecting Model Providers and the models they expose across all in-process LLM roles.
It is the place where a canonical model identity is associated with the capabilities required by a role.
_Avoid_: separate PaperOrchestra provider, caller-local model selection, provider-specific dispatch

**Canonical Model Identity**:
The exact Provider and model identifier that the runtime sends for an inference request, represented as a single `provider/model` reference such as `relay/gpt-5.6-sol`.
It is never a compatibility alias for another model and never determines a Provider through string-prefix guessing.
_Avoid_: legacy model alias, display model name, inferred provider

**Provider Configuration**:
The centrally managed endpoint, supported credential slot, headers, timeout, protocol, and capability metadata for one Model Provider.
A Researcher Model Credential may supply its API key, but callers do not override the remaining Provider Configuration.
_Avoid_: caller-local endpoint, caller-local protocol, arbitrary provider settings, Paper-specific provider

**Provider Connection**:
The System Settings resource that binds a supported Model Provider to its Researcher Model Credential and any endpoint field that Provider explicitly allows the Sole Researcher to configure.
It owns connectivity verification but not model definitions, capability declarations, protocols, retry policy, concurrency policy, or default model selection.
_Avoid_: Unified Model Catalog editor, arbitrary Provider Configuration, model default

**Provider Connection Verification**:
The non-secret result of probing one Provider Connection, recorded against the current credential and endpoint independently from saving them.
It distinguishes unverified, valid, authentication-failed, and unreachable states without deleting or exposing the credential.
_Avoid_: save validation, credential readback, automatic credential deletion

**Researcher Model Credential**:
A Provider-scoped API key the Sole Researcher stores for a configured Model Provider, with at most one stored credential per Provider.
It persists across service restarts but is never returned as plaintext or included in research artifacts, configuration snapshots, logs, exports, or the repository.
It does not define an endpoint, protocol, or model identity.
_Avoid_: arbitrary Provider Configuration, model catalog entry, service credential, artifact

**Effective Model Credential**:
The credential resolved for one Model Provider by preferring its stored Researcher Model Credential and falling back to its supported environment variable only when no stored credential exists.
Its source is observable as `vault`, `environment`, or `missing`, while its plaintext value remains hidden.
_Avoid_: environment override, merged credentials, undisclosed credential source

**Unified Model Runtime**:
The single in-process execution surface that turns semantic model requests into Provider calls for every active consumer.
It owns Catalog resolution, capability validation, adapter selection, telemetry, and error classification; consumers do not create SDK clients or resolve Providers themselves.
_Avoid_: Paper runtime, DR runtime, caller-local client, second factory

**Responses Content Sequence**:
The ordered typed content items within one Responses message, including separate text, image, and file inputs when supported by the selected model.
Its item boundaries and order are part of the requested model context.
_Avoid_: flattened prompt, provider workaround, text-only message

**Active Provider Set**:
The generative Model Providers that the project runtime is allowed to resolve for in-process model calls.
The current generative Active Provider Set contains `relay` and `qwen`; the separately declared `local` embedding implementation is the only non-generative exception.
_Avoid_: every vendored provider, historical provider list, implicit provider

**Active Text Model**:
The one Canonical Model Identity used by every text-producing and text-evaluating role in a run.
Discovery, Deep Research, CodeView, Paper text, candidate selection, and Sci scoring all follow it.
_Avoid_: per-agent text override, role-local model

**Image Model**:
The Capability Model Binding used for PaperOrchestra raster image generation when plotting is enabled.
It is a separate model identity under the same Provider as the Active Text Model.
_Avoid_: image provider, plotting-specific provider

**Model Capability**:
A capability that a model may provide independently, such as text generation, structured output, tool use, vision input, image generation, or embeddings.
Capability support is part of the model's identity and is not assumed merely because two models share an API shape.
_Avoid_: protocol, endpoint, generic model feature

**Capability Model Binding**:
A canonical model identity selected for one capability role, such as the text model or image model.
Different capability bindings may name different models, but the text and image bindings for one run belong to the same Model Provider.
_Avoid_: provider fallback, mixed-provider run, model alias

**Capability Preflight**:
The startup validation that checks the fixed Catalog bindings and their known project eligibility before a run begins.
It also resolves the Effective Model Credential and freshly verifies any Provider Connection whose current validity is not established, blocking research execution when the required connection cannot be validated.
It does not inspect individual requests, infer capabilities dynamically, or choose alternate models.
_Avoid_: per-request negotiation, lazy capability failure, silent downgrade

**Capability Declaration**:
The explicit set of capabilities recorded for one Canonical Model Identity in the Unified Model Catalog.
It documents the model eligibility established during development and is not inferred from individual requests at runtime.
_Avoid_: inferred capability, provider guess, runtime accident

**Protocol Fallback**:
An alternate-protocol retry under the same Provider and Canonical Model Identity.
The current runtime does not use Protocol Fallback; a model has one declared protocol and protocol errors fail explicitly.
_Avoid_: provider fallback, model fallback, silent downgrade

**Background Model Execution**:
Provider-side asynchronous submission and polling for a long model request.
The current runtime does not use it; all model operations complete synchronously and rely on shared timeout, concurrency, and retry policies.
_Avoid_: reasoning in the background, workflow background context, required model capability

**Text Model**:
A model selected for generating or judging textual scientific content, including structured JSON responses and tool-mediated reasoning when supported.
It is selected independently from the Embedding Model even when both are offered by the same Model Provider.
_Avoid_: all-purpose model, primary model

**Embedding Model**:
A model selected to turn text into vectors for Long Memory retrieval.
It may belong to a different Model Provider from the Active Text Model, and its persisted index is disposable and may be deleted and rebuilt when it changes.
_Avoid_: text model, memory provider

**Long Memory Index**:
A disposable retrieval artifact derived from task records and an Embedding Model.
It improves recall but is not authoritative research state and may be discarded without losing the underlying records.
_Avoid_: source of truth, permanent memory database

**Experiment Backend**:
The coding-agent runtime that implements and revises a Candidate Experiment inside its workspace and drives its Experiment Runs.
It is selected independently from a Model Provider.
_Avoid_: Model Provider, Candidate Experiment, model

**Codex CLI Backend**:
The Experiment Backend implemented through Codex's non-interactive command-line coding-agent runtime.
It receives the existing experiment task and workspace contract, edits candidate code, and returns execution output without owning Discovery orchestration, Experiment Run validation, or Model Provider selection.
It is a peer replacement for the Codex CLI Backend at the coding-agent boundary, not a second Unified Model Runtime.
The active Discovery choice is `codex`, and Codex CLI is not retained as a hidden fallback for Discovery.
_Avoid_: Codex Model Provider, Discovery orchestrator, experiment result validator

**Qwen Model Provider**:
The first-class Model Provider for Qwen models.
It is independently selectable from the Qwen Code Backend.
_Avoid_: Qwen Code Backend, Qwen model

**Qwen Code Backend**:
The Experiment Backend implemented through the official Qwen Code coding-agent runtime.
It is a peer of the Codex CLI and iFlow Experiment Backends rather than an alias or mode of either one.
_Avoid_: Qwen Model Provider, Codex CLI Backend, qwen mode

**Paper Candidate Round**:
The most recent completed Discovery Round containing at least one successful Candidate Experiment. Paper candidate comparison is confined to this round.
_Avoid_: last round, globally best round, all rounds

**Terminal Candidate Selection**:
The single post-discovery decision that reduces the Paper Candidate Round to one Selected Research Candidate after every Discovery Round has finished.
_Avoid_: round-to-round baseline selection, continuous reranking, writing-stage selection

**Selected Research Candidate**:
The sole Candidate Experiment whose candidate-local Native Discovery Artifacts enter the Paper Input Bundle when Terminal Candidate Selection succeeds; all of its Experiment Runs remain in scope, while sibling candidates are excluded. Its absence does not block Paper Handoff or paper construction.
_Avoid_: latest candidate, last successful result, all candidates

**Candidate Selection Provenance**:
The auditable record of how the Paper Candidate Round and Selected Research Candidate were determined, including any backward round fallback, model-inferred comparison criterion, or randomized fallback.
_Avoid_: hidden ranking, unexplained best result, selection guess

**Paper**:
The publication-oriented scientific work constructed by one PaperOrchestra Run from a Discovery Launch's Native Discovery Artifacts, optionally centered on a Selected Research Candidate. It may have multiple language editions whose sources and figures remain in that run's workspace.
_Avoid_: paper edition, research draft, launch summary, raw artifact dump

**English Authoritative Edition**:
The English Paper edition completed by PaperOrchestra's native writing, review, and refinement flow. It is the authoritative source for scientific content and for any localized edition.
_Avoid_: English draft, default delivery, translation input draft

**Chinese Companion Edition**:
The automatically produced Simplified Chinese Paper edition that localizes all editable manuscript prose, including captions and appendices, from the completed English Authoritative Edition while preserving equations, citations, bibliography entries, identifiers, code, URLs, numerical values, and raster figure contents. It is an additional delivery and does not replace the English Authoritative Edition as the PaperOrchestra Run's default returned edition.
_Avoid_: Chinese authoritative edition, default returned edition, second Paper, replacement research result

**Native Discovery Artifact**:
A persisted scientific or execution artifact that the normal Discovery workflow produces independently of paper generation, such as a task prompt, candidate method, experiment report, metric record, code file, log, citation record, or figure. Paper-specific capture, model-generated material curation, and PaperOrchestra outputs are not Native Discovery Artifacts.
_Avoid_: Research Draft, Paper Input Bundle, transient model context

**Paper Input Bundle**:
The deterministic, paper-run-local projection of Native Discovery Artifacts into the input shape required by PaperOrchestra. It adds no model-authored scientific content and does not replace its source artifacts.
_Avoid_: Research Draft, new research result, model summary, source of truth

**Paper Idea Brief**:
The method-focused component of a Paper Input Bundle that combines a Discovery Launch's task context with its Selected Research Candidate's method record. It excludes experimental outcomes and competing candidates.
_Avoid_: Experimental Record, Research Draft, complete idea pool

**Experimental Record**:
The results-focused component of a Paper Input Bundle that presents the baseline and every Experiment Run of one Selected Research Candidate in chronological order, including exact measurements and recorded failures. It does not select a best run, calculate new results, or include sibling candidates.
_Avoid_: best-run summary, ablation table, complete Discovery Launch log

**Initial Paper Baseline**:
The control configuration used to evaluate the source-faithful PaperOrchestra port with existing non-code Native Discovery Artifacts only. It excludes Research Drafts, model-authored preprocessing, source code, code summaries, and code differences without deciding whether those inputs may be added later.
_Avoid_: permanent no-code policy, final paper pipeline, Research Draft baseline

**Workflow Progress**:
The persisted collection of Native Discovery Artifacts, PaperOrchestra outputs, and core checkpoints that describes how far a Launch has advanced. It is not a global success/failure verdict; resumption follows the core workflow checkpoints.
_Avoid_: final status, binary launch result, all-or-nothing outcome

**Paper Handoff**:
The one-time transition after all configured Discovery work reaches a terminal outcome. It freezes the Paper Input Bundle assembled from available Native Discovery Artifacts and starts the Launch's PaperOrchestra Run; a Discovery Launch has at most one Paper Handoff.
_Avoid_: Draft Handoff, live shared input, bidirectional synchronization

**Adaptive Argument Structure**:
The top-level organization of a Paper chosen and revised to fit its contribution type, evidence, and scientific argument. It allocates Argument Responsibilities without imposing shared section names or a shared section order across papers.
_Avoid_: fixed chapter template, artifact-order narrative, universal section sequence

**Argument Responsibility**:
A scientific obligation that a completed Paper must satisfy regardless of which section carries it. It is assessed as part of the argument rather than enforced as a heading or position.
_Avoid_: mandatory section, template slot, chapter name

**Argument Density**:
The degree to which manuscript content advances the central scientific argument by establishing claims, evidence, reasoning, comparison, or boundaries. Factual material without an argumentative function lowers density and does not belong merely for record completeness.
_Avoid_: project completeness, information volume, maximal brevity

**Evidence Carrier**:
A manuscript form chosen to carry the support or reasoning for a scientific claim, such as a figure, table, equation, algorithm, or prose. Its value comes from its argumentative function and traceability to authoritative research evidence rather than its presence or count.
_Avoid_: decoration, image slot, figure quota

**Plotting Agent**:
The PaperOrchestra role that autonomously plans, generates, captions, critiques, and revises publication figures from the Paper Input Bundle as part of a PaperOrchestra Run.
_Avoid_: Discovery Agent, experiment backend, figure copier

**Relay Provider**:
The current external OpenAI-compatible Model Provider used by Vegapunk and PaperOrchestra.
It is one selectable provider alongside the Qwen Model Provider, not a PaperOrchestra-specific service boundary.
_Avoid_: OpenAI provider when the configured base URL is a relay, separate Paper provider

**Image Generation Model**:
The capability-specific model exposed by the Relay Provider for synthesizing raster visuals such as method or architecture diagrams. It is distinct from the primary text model but does not introduce a second provider or credential boundary.
_Avoid_: Image Generation Provider, primary text model, plotting agent, vision reviewer

**Paper Template**:
A selectable presentation form for a Paper that controls document class, typography, page design, and localized presentation without prescribing its top-level scientific structure.
_Avoid_: Paper, argument structure, paper schema

**PaperOrchestra Run**:
The single automatically triggered Paper-generation execution owned by a Discovery Launch after Paper Handoff. It constructs that Launch's one Paper and figures; provider retries and upstream in-process retries remain part of the same Run, but the Run has no durable host-restart or stage-resume contract. Re-entry after success returns the existing Paper, while a new Paper requires a new Discovery Launch.
_Avoid_: paper version, retry attempt, independently resumable job

## Discovery Operations

**Discovery LLM Concurrency Limit**:
The fixed number of Discovery model tasks allowed to run simultaneously in the current process. It is set to 2 for the current one-account relay test and must be changed manually before a later run; the process does not negotiate or adapt it at runtime.
_Avoid_: account capacity, retry budget, search concurrency

**Output Token Ceiling**:
An optional upper bound on the total tokens generated for one model response, including reasoning and visible output. When no ceiling is requested, the Responses request leaves the field out and the provider applies its own finite model/context limits.
_Avoid_: visible output length, context window, retry budget
