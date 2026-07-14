# InternAgent

InternAgent coordinates LLM-backed agents for research, discovery, memory, and experiment evaluation.

## Language

**Discovery Launch**:
A bounded research effort that may contain multiple Discovery Rounds and Candidate Experiments. It owns one Research Draft and may produce successive Papers through distinct PaperOrchestra Runs when the Launch is later extended.
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
The Candidate Experiment chosen from the Paper Candidate Round when Discovery can make a terminal selection. Its artifacts provide preferred scientific context to PaperOrchestra, but its absence does not block Draft Handoff or paper construction.
_Avoid_: latest candidate, last successful result, all candidates

**Candidate Selection Provenance**:
The auditable record of how the Paper Candidate Round and Selected Research Candidate were determined, including any backward round fallback, model-inferred comparison criterion, or randomized fallback.
_Avoid_: hidden ranking, unexplained best result, selection guess

**Paper**:
The publication-oriented LaTeX/PDF product constructed by one PaperOrchestra Run from a Discovery Launch's Research Draft and authoritative artifacts, optionally informed by a Selected Research Candidate. Its sources and figures remain in that run's workspace alongside the final PDF.
_Avoid_: Research Draft, launch summary, raw artifact dump

**Research Draft**:
The mandatory launch-local Markdown record at `manuscript/draft.md` that begins with the Launch's complete initial research inputs and then appends exhaustive, self-contained blocks from the Discovery process. Capture starts as soon as the Launch exists, before any Agent, model, tool, or experiment work. It has no independent checkpoint or resume state; resumed core work simply appends more blocks, and replay may create duplicates. Draft capture stops when the currently configured Discovery work reaches Draft Handoff. If that Launch is later explicitly extended and resumed, capture resumes by appending to the same Draft; PaperOrchestra activity never appends back into it.
_Avoid_: Living Manuscript, Paper, activity log

**Draft Block**:
One append-only Markdown unit representing one Observable Research Event, such as a model call, tool call, tool result, error, or completed stage output. Blocks contain no semantic metadata or editorial envelope; a fixed non-rendered delimiter separates adjacent raw event content. Every mathematical expression is preserved verbatim, including notation, delimiters, definitions, assumptions, and derivation steps, without semantic filtering or editorial restructuring.
_Avoid_: summary, chapter, manuscript section, filtered log entry

**Observable Research Event**:
A meaningful event exposed by the current research runtime, including Agent lifecycle, model traffic, tool traffic, subprocess execution, Discovery stage or round transitions, explicitly reported artifact creation or updates, and text actually emitted through the Discovery process's Python logging, standard-output, or standard-error channels. Capture does not scan directories before and after opaque work or duplicate changed artifact contents into the Draft; those files remain authoritative under the Launch root supplied to PaperOrchestra. An opaque backend's unexposed internal events are outside this boundary: for the initial Claude Code integration, capture sees the invocation, prompt, process result, errors, and final JSON response but does not change the existing invocation to expose its internal event stream. Operating-system syscalls, lock contention, and scheduler activity are not Observable Research Events.
_Avoid_: syscall trace, debug noise, inferred event, semantic summary

**Observable Model Context**:
The prompts, instructions, visible responses, structured outputs, tool calls, tool results, and visible stream fragments exposed by a model runtime. It excludes hidden model reasoning and makes no claim to capture it.
_Avoid_: chain of thought, hidden reasoning, inferred intention

**Workflow Progress**:
The persisted collection of Research Draft blocks, research artifacts, PaperOrchestra outputs, and core checkpoints that describes how far a Launch has advanced. It is not a global success/failure verdict; resumption follows the core workflow checkpoints, while Draft capture remains an append-only side effect.
_Avoid_: final status, binary launch result, all-or-nothing outcome

**Draft Handoff**:
The one-way transition after all currently configured Discovery work reaches a terminal outcome. It appends the final event, stops Draft capture, and supplies PaperOrchestra with the absolute Research Draft path, Launch root, and optional candidate-selection path without a Discovery-side raw-material conversion layer. Explicitly extending and resuming a previously handed-off Launch may produce a later handoff from the expanded Draft; it does not alter the earlier PaperOrchestra Run.
_Avoid_: live shared input, bidirectional synchronization, writing-event capture

**Agent Task Completion**:
The boundary at which an Agent reaches the final success or final failure of one bounded assigned task and returns its coherent result or exhausted-failure context to its caller, regardless of whether that outcome proves useful to the launch's draft record. It is finer-grained than a Discovery stage but does not include model calls, tool operations, intermediate errors, retries, or partial outputs inside an unfinished Agent task.
_Avoid_: Research-Significant Action, success-only completion, intermediate retry

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

**Presentation Transformation**:
A deterministic rendering of already recorded evidence into an Evidence Carrier that preserves its scientific meaning and creates no new measurement, metric, aggregation, statistical inference, or selection judgment.
_Avoid_: new analysis, experiment, data repair

**Plotting Agent**:
The PaperOrchestra role that plans, generates, critiques, and corrects the full range of paper figures, including evidence-backed statistical plots and explanatory method diagrams. It consumes the Research Draft and authoritative artifacts but is not part of Discovery capture and does not perform literature research. Textual planning and visual criticism use InternAgent's primary Model Runtime, while raster image generation may use the separately configured Image Generation Provider.
_Avoid_: figure copier, Draft capture hook, Manuscript Sculptor

**Image Generation Provider**:
The separately configured external model service used only when the Plotting Agent must synthesize raster visuals such as method or architecture diagrams. Its credentials are runtime secrets and are not part of the Research Draft, repository configuration, or primary text-model credential path.
_Avoid_: primary Model Runtime, plotting agent, vision reviewer, committed API key

**Paper Template**:
A selectable presentation form for a Paper that controls document class, typography, page design, and localized presentation without prescribing its top-level scientific structure.
_Avoid_: Paper, argument structure, paper schema

**PaperOrchestra Run**:
One automatically triggered, independently resumable execution of PaperOrchestra for a particular Draft Handoff that constructs a Paper and its figures. It may read the Research Draft in delimiter-aligned batches and persist disposable working material so model context limits do not require truncating the canonical Draft. Re-entry for that same handoff resumes the same run, while a later handoff after additional Discovery creates a new run and preserves every earlier run unchanged. Its checkpoints contribute to Workflow Progress and never rewrite the Research Draft.
_Avoid_: discovery round, experiment run, report generation
