# Vegapunk

Vegapunk coordinates LLM-backed agents for research, discovery, memory, and experiment evaluation.

## Language

## Product Experience

**Unified Workspace**:
The one desktop browser interface for Vegapunk, organized as a persistent module sidebar, a central work area, and an optional artifact preview area.
It has no administrator or user-facing shell, no sign-in, and no role-specific navigation.
_Avoid_: Admin Console, Researcher Workspace, user-facing interface

**Sole Researcher**:
The one person allowed to use the Version 1 product's curated research capabilities.
Every Version 1 request is implicitly theirs; the product has no sign-in, registration, invitation, account-management, or multi-user flows.
_Avoid_: Invited Researcher, public user, multi-user account

**Intranet Product Boundary**:
The Version 1 deployment boundary that serves the Unified Workspace as a Web application from an internal-network server to the Sole Researcher.
It excludes public Internet exposure and multi-account product access; a later expansion beyond the Sole Researcher requires a separate identity and authorization decision.
_Avoid_: local-only product, public deployment, multi-user account

**Desktop Web Console**:
The Unified Workspace as accessed in a desktop browser, through which a researcher configures, starts, observes, and reviews research work.
It is a desktop-only product surface rather than a responsive mobile application and does not imply that research execution runs on the user's device.
_Avoid_: mobile app, touch-first layout, local CLI, execution node

**Desktop-First Web Workspace**:
The Intranet Product Boundary delivered through a desktop browser rather than a native desktop application.
It has no mobile product experience in Version 1, while a future native application remains an independent product decision.
_Avoid_: native desktop app, mobile client, desktop-only deployment

**Desktop Visual Baseline**:
The 1440 CSS-pixel-wide desktop browser viewport used to compose the Unified Workspace's primary visual hierarchy, whitespace, and research texture.
The workspace remains functionally complete at 1024 CSS pixels without a separate compact visual system, while narrower viewports receive only basic overflow protection.
_Avoid_: mobile-first composition, native-window assumption, false 1024px parity

**Workspace Module**:
A top-level capability area selected from the Unified Workspace sidebar, such as Conversations, Skill Management, Project Space, or System Settings.
Each module owns the central work area while the sidebar remains stable.
_Avoid_: role-specific console, page chrome, artifact preview

**Paper Tools**:
A Workspace Module selected from the Unified Workspace sidebar for finding and later working with scholarly papers.
Its Version 1 surface contains the Paper Search, Paper Deep Reading, and Citation Verification Paper Tool Submodules.
All three Version 1 submodules are visible placeholders until a stable paper-service design is selected.
_Avoid_: paper artifact preview, literature source, research project

**Paper Tool Submodule**:
One of the three child capability areas within Paper Tools.
Paper Tool Submodules use the Paper Tools' internal tab navigation and are not separate Workspace Modules or sidebar destinations.
_Avoid_: Workspace Module, independent route, sidebar module

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

**Researcher Skill**:
A reusable Skill created and owned by the Sole Researcher through the top-level Skill Management Workspace Module.
_Avoid_: system Prompt, built-in Prompt, internal orchestration Prompt

**Artifact Preview**:
The contextual right-side area of the Unified Workspace that appears when a selected non-PDF artifact has a previewable representation.
It remains absent when no artifact is selected and does not replace the central work area.
_Avoid_: Browser PDF Reader, full-screen reader, artifact explorer, permanent third column

**Browser PDF Reader**:
The browser-native PDF viewer opened in a new tab for every user-visible PDF artifact.
It replaces all PDF uses of Artifact Preview and embedded artifact viewing.
Browser configuration determines the reader implementation and whether a user downloads the file instead.
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

**Rice-White Workspace**:
The Unified Workspace visual foundation of warm rice-white surfaces, graphite text, restrained rules, and a Unified Tonal Spectrum for non-error interface signals.
Navigation belongs to the same continuous light field as the work area rather than becoming a dominant dark rail.
Local Material Expression Layers may enrich this foundation without replacing it with a persistent dark theme.
_Avoid_: dark dashboard shell, stark cool-white surface, a separate blue identity spectrum, competing semantic accent colors

**Material Expression Layer**:
A localized visual layer above the Rice-White Workspace that applies a selected craft or art material vocabulary to frame research identity, object focus, or exhibition-oriented content.
It remains subordinate to text, controls, real charts, and explicit state indicators, and never substitutes for a real research measurement or lifecycle state.
_Avoid_: global recoloring, decorative wallpaper, implicit data visualization, themed controls on every surface

**Maki-e Research Expression**:
The only directly recognizable Material Expression Layer in the initial visual system.
It draws on Maki-e's material precision, controlled powder-like aggregation, and compositional restraint rather than reproducing historical motifs.
Other art forms may inform its whitespace, asymmetry, or texture principles, but may not appear as independently recognizable visual languages.
_Avoid_: Japanese-style collage, literal traditional motifs, a second named art direction

**Exhibition Module**:
A Workspace Module whose primary job is to frame research context, progress, or outputs rather than support dense configuration work.
Project Space is the Version 1 Exhibition Module and uses a stronger distributed Research Identity Layer in its title, structural whitespace, and current-object states while operational modules remain visually quiet.
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
The motion discipline for Deterministic Identity Graphics: static by default, with a brief low-amplitude response only on meaningful entry, project-change, or direct-hover events.
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
The persistent, static, and clearly perceptible Unified Tonal Spectrum point-cloud composition anchored to the lower-right of the Unified Workspace's main content background.
Foreground panels, records, and content naturally crop and occlude it, so it remains a single shared research-identity subject without competing with reading or controls.
_Avoid_: random redraws, full-bleed particle wallpaper, overlap with text or inputs, a generic star field

**Stable Particle Identity**:
The deterministic particle distribution assigned to one Workspace Module or research object.
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
The rule that all interface elements share the Research Texture Set while only Workspace Modules, research objects, workflow groups, and the current record receive their own Stable Particle Identity.
Individual static cards and parameter rows use common local texture rather than independent visual signatures.
_Avoid_: one illustration per card, record-level visual clutter, noisy catalogue

**Particle Semantic Boundary**:
The prohibition on using particle count, density, or motion as an implicit representation of quantities, completion, research progress, or scientific results.
Particles express identity, interface hierarchy, and permitted interaction states only; real information remains explicit text, controls, charts, or labelled visualizations.
_Avoid_: atmospheric progress indicator, ambiguous quantitative texture, decorative telemetry

**Particle Intensity Gradient**:
The allocation of particle emphasis by Workspace Module: low in System Settings and Prompt Library, medium in Conversations and Skill Management, and high in Project Space.
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
_Avoid_: Task Authoring Form, Paper Input Bundle, Launch Workspace

**Staged Research Upload**:
A temporary input file stored before one Deep Research Run or Discovery Launch claims it during creation.
It may be claimed once, while an unclaimed upload expires; it is neither a reusable file library nor a research artifact.
_Avoid_: attachment library, permanent upload, research artifact, shared input

**Prompt Library**:
The single service-wide collection of every editable Prompt text in the system, stored as repository source files and including scientific-behavior prompts and infrastructure/scaffolding prompts.
Each new Deep Research Run or Discovery Launch reads it when it starts; edits affect work that starts afterwards and never change work already running.
There are no per-Launch prompt overrides.
Saved Prompt revisions have no built-in history or system-original copy; repository history owns recovery after a successful save.
_Avoid_: per-Launch prompt snapshot, mid-run prompt edit, hardcoded prompt, curated prompt subset

**Registered Prompt**:
A Prompt Library entry with a stable identity and runtime call site supplied by the installed Vegapunk version.
The Sole Researcher may revise its content but cannot edit its system-maintained metadata or create, delete, or rename Registered Prompts through System Settings.
_Avoid_: ad hoc Prompt, user-created Prompt, unregistered Prompt

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
The service-wide catalog of every run parameter and its default, description, type, and validation rule, managed through the Unified Workspace.
Only intentionally configurable parameters with stable identities belong to the Registry; secrets, internal paths, protocol details, and implementation constants do not.
An allowlisted subset may be supplied as Researcher Run Settings without changing the Registry defaults.
_Avoid_: raw config file editing, unrestricted researcher override, mid-run change, undocumented parameter

**Settings Activation Boundary**:
The start of the next new Deep Research Run or Discovery Launch, when committed System Settings changes become effective without requiring a service restart.
Work already running retains the settings resolved at its own start.
Queued work has not crossed this boundary and therefore uses the latest committed settings when it starts, while a Launch Resume continues to use its original Launch Configuration Snapshot.
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

**Launch Queue**:
The service-wide first-in-first-out order in which submitted Discovery Launches wait to execute. Exactly one Launch runs at a time; submitting a Launch enqueues it rather than starting it immediately.
_Avoid_: parallel launches, per-user queue, immediate start

**Graceful Stop**:
The default way to stop running research work: it finishes its current smallest unit, persists any supported checkpoint, and exits with the work marked stopped without triggering later stages.
A stopped Discovery Launch may resume, while a stopped Deep Research Run requires a new Run; force kill remains an Admin-only fallback.
_Avoid_: default hard kill, pause, wait-for-round-completion

**Interrupted Launch**:
A Discovery Launch whose execution ended without a trustworthy terminal outcome.
Its durable progress is reconciled first; if it did not complete, the Sole Researcher may explicitly resume it, but the product never resumes it automatically.
_Avoid_: failed Launch, aborted Launch, automatic resume

**Launch Resume**:
Re-enqueueing a stopped or reconciled-incomplete Interrupted Launch to continue from its Workflow Progress checkpoints using exactly the prompts and parameters captured at its original start.
It requires an explicit researcher action, preserves earlier Execution Attempts, adds a new attempt at the current milestone, and never absorbs later Prompt, model-binding, or run-parameter edits.
Each resumed Execution Attempt resolves the current Provider Connection for the originally bound Provider because credentials are never stored in the Launch Configuration Snapshot.
_Avoid_: new Launch, automatic resume, mixed-configuration continuation, edit absorption on resume

**Research Progress Timeline**:
The durable ordered chain of core milestones through which the product presents one Deep Research Run or Discovery Launch.
Milestone state changes are the product's persisted progress events, so live and reopened views share one record while detailed operational output remains in the Research Activity Stream.
_Avoid_: transient progress, raw internal trace, replacement for activity output

**Research Activity Stream**:
The bounded durable terminal-style sequence of curated and redacted operational messages for one Deep Research Run or Discovery Launch.
It complements the Research Progress Timeline, resumes after reconnect, may discard its oldest messages at the product limit, and never exposes raw Admin logs, hidden prompts, or internal reasoning.
_Avoid_: raw Admin log, internal trace, replacement for progress milestones

**Execution Attempt**:
One contiguous execution of a Research Progress Timeline milestone.
A Discovery Launch Resume adds an attempt while preserving earlier attempts; an Execution Attempt is not an Experiment Run.
_Avoid_: Experiment Run, resumed Launch, overwritten attempt

**Live Launch View**:
The Unified Workspace view that follows the currently running Discovery Launch in real time: its current stage and round, each runtime artifact as soon as it is persisted, and streaming key logs. It does not wait for stage or Launch completion.
_Avoid_: post-hoc report, final-artifact-only view, completed-Launch browser

**Artifact Explorer**:
The Unified Workspace surface that exposes every file a Launch persists as a browsable tree with content viewers, guaranteeing that all runtime artifacts are reachable. Structured views such as the Launch timeline and Experiment Run detail are navigational overlays on top of it, never the only path to an artifact.
_Avoid_: curated artifact list, final-only gallery, unmodeled-file blind spot

**Curated Research Artifact**:
A stable product-visible output selected from one Deep Research Run or Discovery Launch and addressed by an opaque artifact identity rather than a filesystem path.
It excludes raw logs, hidden prompts, internal configuration, temporary files, and unrestricted workspace content.
_Avoid_: Artifact Explorer entry, arbitrary file path, raw runtime artifact

**Reproducibility Bundle**:
The sanitized downloadable package of code, effective non-secret settings, metrics, and instructions needed to reproduce a completed Discovery Launch's selected experimental result.
It is a Curated Research Artifact rather than a copy of the complete Launch workspace.
_Avoid_: full workspace archive, raw artifact dump, configuration snapshot

**Task Authoring Form**:
The Unified Workspace form through which the researcher directly composes a research task's structured fields (system, task description, domain, background, constraints) and uploads its baseline code package. It performs no LLM assistance; a task without baseline code can only take the report path, not the experiment path.
_Avoid_: Task Builder, automatic task generation, topic-only quick start

**Task Builder**:
The planned later capability that turns a research topic plus uploaded reference materials into a draft task via model assistance, for researcher review before enqueueing. It is not part of the first Unified Workspace delivery.
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

**Qwen Model Provider**:
The first-class Model Provider for Qwen models.
It is independently selectable from the Qwen Code Backend.
_Avoid_: Qwen Code Backend, Qwen model

**Qwen Code Backend**:
The Experiment Backend implemented through the official Qwen Code coding-agent runtime.
It is a peer of the Claude Code and iFlow Experiment Backends rather than an alias or mode of either one.
_Avoid_: Qwen Model Provider, Claude Code Backend, qwen mode

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
