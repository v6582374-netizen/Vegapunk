# InternAgent

InternAgent coordinates LLM-backed agents for research, discovery, memory, and experiment evaluation.

## Language

**Default LLM**:
The chat or reasoning model selected when callers do not provide an explicit model for an OpenAI-compatible text workflow. It does not include embedding models, local/HuggingFace models, provider-specific presets, or modality-specific audio/realtime models.
_Avoid_: default model, base model

**Discovery Round**:
One launch-level iteration in which InternAgent proposes research ideas and processes them through the selected workflow mode. It is a sequential evolution step, not a tree-search node.
_Avoid_: evolution node, tree node, search node

**Candidate Experiment**:
A single research idea selected for execution or evaluation within a Discovery Round. Multiple Candidate Experiments may exist in the same round.
_Avoid_: round, node, final report

**Experiment Run**:
One numbered attempt inside a Candidate Experiment to implement, execute, and collect results. Experiment Runs are lower-level than Discovery Rounds.
_Avoid_: discovery round, candidate

**Experiment Report**:
A concise factual account of the runs and results for one Candidate Experiment. It is not the launch-level final paper.
_Avoid_: final report, final paper, paper artifact

**Launch Summary**:
The launch-level completion record that aggregates Discovery Rounds, Candidate Experiments, and their success status. It is an index of what happened, not a scientific narrative.
_Avoid_: final report, paper

**Final Paper Artifact**:
A polished launch-level paper output generated after discovery has selected a final successful result. It should be distinct from intermediate Experiment Reports.
_Avoid_: experiment report, discovery summary, sci report

**Best Successful Candidate**:
The successful Candidate Experiment selected across an entire launch as the source for the Final Paper Artifact. When comparable performance data exists, it is the successful candidate with the highest score.
_Avoid_: final best code path, latest successful result, last candidate

**Launch Model**:
The single provider and text-generation model selected for all InternAgent-managed LLM calls within one discovery launch. It does not include embedding models, rerankers, LaTeX compilation, shell execution, or external non-text-generation tools.
_Avoid_: paper model, scorer model, experiment model

**Paper Artifact Status**:
The user-facing outcome of Final Paper Artifact generation. The allowed statuses are `success`, `partial`, `skipped`, and `failed`.
_Avoid_: boolean success, report status
