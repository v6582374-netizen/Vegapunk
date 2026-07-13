# InternAgent

InternAgent coordinates LLM-backed agents for research, discovery, memory, and experiment evaluation.

## Language

**Discovery Launch**:
A bounded research effort that may contain multiple Discovery Rounds and Candidate Experiments. It is the aggregation boundary for at most one Research Dossier.
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
The Candidate Experiment chosen from the Paper Candidate Round whose existing artifacts form the primary scientific subject of a Research Dossier.
_Avoid_: latest candidate, last successful result, all candidates

**Candidate Selection Provenance**:
The auditable record of how the Paper Candidate Round and Selected Research Candidate were determined, including any backward round fallback, model-inferred comparison criterion, or randomized fallback.
_Avoid_: hidden ranking, unexplained best result, selection guess

**Research Dossier**:
The canonical final product for one Discovery Launch, combining a publication-oriented Research Narrative with authoritative research evidence and companion reproducibility material centered on its Selected Research Candidate.
_Avoid_: final paper, manuscript, launch summary

**Research Narrative**:
The publication-oriented LaTeX/PDF view of a Research Dossier that presents a coherent scientific contribution and the evidence needed to assess it while remaining traceable to the authoritative evidence.
_Avoid_: research dossier, canonical evidence, raw artifact dump

**Living Manuscript**:
The single evolving paper draft, including its bibliography and Evidence Carriers, maintained throughout a Discovery Launch. Before Terminal Candidate Selection it is organized around the launch's research question and baseline; afterward it is refocused around the Selected Research Candidate, and its latest validated state at launch completion is the synchronized paper output.
_Avoid_: final paper, research dossier, raw activity log

**Agent Task Completion**:
The boundary at which an Agent reaches the final success or final failure of one bounded assigned task and returns its coherent result or exhausted-failure context to its caller, regardless of whether that outcome proves useful to the Living Manuscript. It is finer-grained than a Discovery stage but does not include model calls, tool operations, intermediate errors, retries, or partial outputs inside an unfinished Agent task.
_Avoid_: Research-Significant Action, success-only completion, intermediate retry

**Sculptor Context Fork**:
The exact observable context transferred from a research Agent into a newly invoked Manuscript Sculptor before the source context is discarded. It preserves the source instructions, messages, tool interactions, tool results, and direct outputs without an intervening summary, while authoritative artifacts remain available for evidence verification; it neither includes nor claims access to hidden model reasoning.
_Avoid_: research summary, path-only trigger, hidden chain of thought

**Sculptor-Capable Agent Runtime**:
An Agent runtime that can create a distinct Manuscript Sculptor invocation from a source task's complete observable context while preserving the Sculptor's dedicated prompt and narrower authority. Returning only a summary, final response, log, or artifact path does not satisfy this capability.
_Avoid_: best-effort context transfer, stdout handoff, path fallback

**Sculptor Completion Barrier**:
The boundary that keeps a completed source Agent task and its observable context alive until its Manuscript Sculptor invocation has edited and validated the canonical Living Manuscript. It serializes manuscript mutations without preventing other Agents whose tasks are still running from continuing their research.
_Avoid_: asynchronous writing queue, post-stage batch, global research lock

**Sculptor Invocation**:
The single top-level authoring execution that InternAgent forks and awaits for one Agent Task Completion. Any internal delegation, parallel Agents, or coordination used by the selected Agent backend remains part of that one invocation and is neither orchestrated nor recursively hooked by InternAgent.
_Avoid_: project-managed writer swarm, Editorial Subagent, recursive Sculptor trigger

**Manuscript Sculptor**:
The dedicated authoring role that evaluates each Sculptor Context Fork against the Living Manuscript and freely decides whether and how to add, remove, revise, reorganize, or leave content unchanged until the strongest publication-oriented account supported by the supplied evidence is coherent. Its dedicated prompt constrains the accepted manuscript state rather than edit modes; it may create Presentation Transformations from supplied evidence but cannot initiate or request research and owns neither evidence validity, scientific analysis, experiment judgment, nor candidate selection.
_Avoid_: one-shot paper writer, research agent, peer reviewer

**Manuscript Sculptor Prompt**:
The dedicated prompt injected before every Manuscript Sculptor writing action to constrain its editorial objective, authority, style, and completion conditions. It is a mandatory role instruction rather than a reusable or optionally invoked skill.
_Avoid_: skill, optional prompt, orchestration state

**Adaptive Argument Structure**:
The top-level organization of a Living Manuscript chosen and revised to fit its contribution type, evidence, and scientific argument. It allocates Argument Responsibilities without imposing shared section names or a shared section order across papers.
_Avoid_: fixed chapter template, artifact-order narrative, universal section sequence

**Argument Responsibility**:
A scientific obligation that a completed Research Narrative must satisfy regardless of which section carries it. It is assessed as part of the argument rather than enforced as a heading or position.
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

**Research Narrative Template**:
A selectable presentation form for a Research Narrative that controls document class, typography, page design, and localized presentation without prescribing its top-level scientific structure.
_Avoid_: research narrative, argument structure, dossier schema

**Dossier Run**:
One optional, independently executable and resumable post-launch attempt to optimize or re-render the Research Narrative from a completed Discovery Launch. Its outcome does not change the Discovery Launch or its synchronized Living Manuscript.
_Avoid_: discovery round, experiment run, report generation
