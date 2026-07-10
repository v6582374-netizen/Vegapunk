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
The canonical final product for one Discovery Launch, combining authoritative research evidence with a self-explaining Research Narrative centered on its Selected Research Candidate.
_Avoid_: final paper, manuscript, launch summary

**Research Narrative**:
The human-readable LaTeX/PDF view of a Research Dossier that explains the method, results, research process, and reproduction path while remaining traceable to the authoritative evidence.
_Avoid_: research dossier, canonical evidence, raw artifact dump

**Research Narrative Template**:
A selectable presentation form for a Research Narrative. Every template implements the same top-level content contract and may change appearance or localized labels but not the semantic responsibilities of those sections.
_Avoid_: research narrative, dossier schema, template-specific content model

**Dossier Run**:
One independently executable and resumable attempt to assemble the Research Dossier and render its Research Narrative for a Discovery Launch. Its outcome does not change the outcome of the Discovery Launch.
_Avoid_: discovery round, experiment run, report generation
