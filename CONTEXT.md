# InternAgent

InternAgent coordinates LLM-backed agents for research, discovery, memory, and experiment evaluation.

## Language

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
The single third-party OpenAI-compatible model service through which every PaperOrchestra model call is routed. It owns one base URL and credential boundary while exposing multiple capability-specific model IDs and endpoints.
_Avoid_: one model, separate image provider, upstream Gemini provider

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
