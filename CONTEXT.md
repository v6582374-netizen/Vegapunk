# Vegapunk

Vegapunk coordinates LLM-backed agents for research, discovery, memory, and experiment evaluation.

## Language

## Product Experience

**Admin Console**:
The current Desktop Web Console deliverable: a developer-facing administration interface that exposes every prompt, run parameter, and runtime artifact of Vegapunk for testing and modification.
It serves the project developer, has no accounts, and is not the future end-user product; a user-facing console with a curated surface is a separate later deliverable.
_Avoid_: end-user console, public product, curated interface

**Sole Researcher**:
The one person allowed to use the Version 1 product's curated research capabilities.
Every Version 1 request is implicitly theirs; the product has no authentication, invitation, registration, account-management, or multi-user flows, and product access remains distinct from Admin Console privileges.
_Avoid_: Invited Researcher, authenticated principal, anonymous public user, multi-user account

**Local Product Boundary**:
The Version 1 access boundary that confines the product and its API to the Sole Researcher's own machine and same-origin browser context.
It excludes LAN and public access; remote access requires a later authentication decision.
_Avoid_: public deployment, LAN service, unauthenticated remote access

**Desktop Web Console**:
The browser-based product interface through which a researcher configures, starts, observes, and reviews research work from a desktop operating system.
It excludes a mobile client and does not imply that research execution runs on the user's device.
_Avoid_: mobile app, local CLI, execution node

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
The single service-wide collection of every editable prompt text in the system, including scientific-behavior prompts and infrastructure/scaffolding prompts. A Discovery Launch reads it when it starts; edits affect Launches that start afterwards and never change a running Launch. There are no per-Launch prompt overrides.
_Avoid_: per-Launch prompt snapshot, mid-run prompt edit, hardcoded prompt, curated prompt subset

**Run Parameter Registry**:
The service-wide catalog of every run parameter and its default, description, type, and validation rule, edited through structured forms in the Admin Console.
An allowlisted subset may be supplied as Researcher Run Settings without granting access to the Registry or changing its defaults.
_Avoid_: raw config file editing, unrestricted researcher override, mid-run change, undocumented parameter

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
It requires an explicit researcher action, preserves earlier Execution Attempts, adds a new attempt at the current milestone, and never absorbs later configuration edits.
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
The Admin Console view that follows the currently running Discovery Launch in real time: its current stage and round, each runtime artifact as soon as it is persisted, and streaming key logs. It does not wait for stage or Launch completion.
_Avoid_: post-hoc report, final-artifact-only view, completed-Launch browser

**Artifact Explorer**:
The Admin Console surface that exposes every file a Launch persists as a browsable tree with content viewers, guaranteeing that all runtime artifacts are reachable. Structured views such as the Launch timeline and Experiment Run detail are navigational overlays on top of it, never the only path to an artifact.
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
The Admin Console form through which the developer directly composes a research task's structured fields (system, task description, domain, background, constraints) and uploads its baseline code package. It performs no LLM assistance; a task without baseline code can only take the report path, not the experiment path.
_Avoid_: Task Builder, automatic task generation, topic-only quick start

**Task Builder**:
The planned later capability that turns a research topic plus uploaded reference materials into a draft task via model assistance, for developer review before enqueueing. It is not part of the first Admin Console delivery.
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

**Researcher Model Credential**:
A Provider-scoped API key the Sole Researcher stores for an administrator-approved Model Provider and selects for their work.
It does not define an endpoint, protocol, or model identity and remains distinct from research artifacts and configuration snapshots.
_Avoid_: arbitrary Provider Configuration, model catalog entry, service credential, artifact

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
