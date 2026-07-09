# Final Paper as a Post-Launch Artifact

InternAgent will treat the final paper as a launch-level artifact generated after discovery completes, rather than modifying or replacing per-candidate experiment reports. This keeps Discovery Rounds, Candidate Experiments, Experiment Runs, and sci-task reproduction reports on their existing paths while giving the selected final successful result a separate `final_paper/` output boundary for LaTeX, PDF, and provenance metadata.

The finalizer will choose the Final Paper Artifact source from all successful Candidate Experiments in the launch. When candidates have comparable performance data, the selected source is the Best Successful Candidate with the highest score rather than the last successful candidate or the incremental baseline handoff path.

The finalizer may use an LLM to formalize the selected result into a paper-like narrative, but the generation must be source-constrained. Its allowed inputs are existing launch and candidate artifacts such as `discovery_summary.json`, `notes.txt`, `experiment_report.txt`, `run_N/final_info.json`, figures, and logs; it must not introduce new experiments, new metrics, or unsupported conclusions.

Paper generation will be explicitly enabled by configuration instead of becoming an unconditional discovery side effect. If final paper generation or PDF compilation fails, the launch remains successful as long as discovery itself completed; the failure is recorded as a paper-artifact failure rather than a discovery failure.

The first implementation will only support `mode=experiment` with `task_type=auto`. It will not attach to `mode=report`, because that path writes idea-only reports without experiment results, and it will not attach to `task_type=sci`, because sci tasks already use `report/report.md` for paper reproduction and scoring.

The finalizer will generate `paper.tex` directly from the selected source artifacts rather than introducing a Markdown paper draft as an intermediate layer. `paper.tex` and `paper_manifest.json` are core outputs; `paper.pdf` is a derived output that exists only when LaTeX compilation succeeds. If compilation fails, the finalizer should use the Launch Model to repair LaTeX compile errors in place before giving up.

LaTeX compile repair will be bounded to three attempts in the first implementation. After the third failed repair attempt, the finalizer preserves `paper.tex`, the compile log, and `paper_manifest.json`, reports `partial`, and tells the user that the paper source was saved but PDF compilation could not be completed automatically.

The repair-attempt limit may be exposed as a paper behavior setting, defaulting to `max_compile_repair_attempts: 3`. This setting does not affect Launch Model selection.

The first implementation will use a fixed output layout under the launch output directory: `final_paper/paper.tex`, `final_paper/paper.pdf`, `final_paper/paper_manifest.json`, `final_paper/compile.log`, and `final_paper/sources/` for compile-time assets such as figures. The finalizer should not copy the entire selected candidate directory into `final_paper/`; provenance paths belong in the manifest.

The finalizer may discover candidate figures from the Best Successful Candidate directory using common image extensions such as `.png`, `.jpg`, `.jpeg`, and `.pdf`, while excluding caches, virtual environments, and repository metadata. It should copy only a small bounded set of compile-time assets into `final_paper/sources/` and let the Launch Model decide which discovered figures belong in the paper body.

References will be conservative in the first implementation. The finalizer may reuse references, URLs, paper titles, or BibTeX already present in source artifacts, but it must not browse for new references during finalization and must not let the Launch Model invent citations.

The finalizer will build a deterministic `source_bundle.json` as the prompt input snapshot for the selected result. The bundle may include the selected candidate record from `discovery_summary.json`, `notes.txt`, `experiment_report.txt`, baseline and latest-run `final_info.json`, figure inventory, and small launcher/config summaries, but it should not dump entire logs, full code trees, or failed-candidate noise into the paper prompt.

Code context in `source_bundle.json` will be conservative in the first implementation. The finalizer may include key file paths and a small implementation summary derived from existing notes or reports, but it should not include full source files or large diffs in the paper prompt.

The first implementation will generate the paper body in Chinese. Because the default conference template is ICLR 2026, the renderer and compiler must account for Chinese text support rather than assuming an English-only LaTeX document.

Chinese paper generation will prefer the `iclr2026` template with XeLaTeX-compatible Chinese support. If the conference template and Chinese support cannot be made to compile within the bounded repair loop, the finalizer preserves the TeX source and reports `partial` rather than failing discovery.

The Launch Model will generate a Chinese paper title and abstract from the selected source bundle. The first implementation will use `InternAgent` as the author, use the launch completion date as the paper date, and require the abstract to cover method, experimental setup, main results, and limitations.

The paper narrative will center on the Best Successful Candidate. The broader launch process may appear as provenance or lightweight selection context, but failed candidates and round-by-round evolution should not dominate the paper body.

Failed candidates will be treated as provenance rather than paper evidence in the first implementation. The paper body may briefly state the successful-candidate selection rule, while detailed failed-candidate information belongs in `paper_manifest.json`.

LaTeX templates will be managed as optional project resources under `tex_templates/`. The first available conference-style template is the official ICLR 2026 template, kept under `tex_templates/iclr2026/`, and later templates can be added beside it without changing discovery output paths.

The implementation will live behind a narrow `paper_artifact` module boundary. `launch_discovery.py` should only call the finalizer after `discovery_summary.json` is written and paper generation is enabled; candidate selection, source gathering, LLM formalization, LaTeX rendering, PDF compilation, and manifest writing belong inside the paper artifact module rather than in the launch script or `ReportWriter`.

The first implementation will only trigger for future launches as part of the normal discovery completion path. It will not include a standalone backfill workflow for historical launch directories, because existing historical artifacts may be incomplete and are not required for the initial integration.

Paper formalization must use the Launch Model rather than introducing a separate paper model setting. Over time, other InternAgent-managed text LLM calls such as experiment coding and sci scoring should also derive from the Launch Model; model-specific fields such as `experiment.model` and `sci_task.scorer_model` are compatibility fallbacks rather than independent sources of truth. Embedding models, rerankers, LaTeX compilation, shell execution, and non-text-generation tools are outside the Launch Model boundary.

The first paper-artifact implementation will not refactor existing experiment-backend or sci-scoring model paths. It will only ensure that the new paper finalizer does not introduce another independent model setting.

The paper finalizer must call the Launch Model through the existing InternAgent model abstraction, such as `internagent.mas.models.model_factory.ModelFactory` and the `BaseModel` interface. The paper artifact module must not directly instantiate OpenAI/OpenRouter clients or read provider API keys, because doing so would bypass the repository's model-provider boundary.

Best Successful Candidate selection will use `performance.overall_improvement_rate` when at least one successful candidate has a comparable score. Ties are resolved deterministically by preferring the later Discovery Round and then the earlier candidate order in `discovery_summary.json`. If no successful candidate has a comparable score, the finalizer skips paper generation, writes `paper_manifest.json` with `selection_status: "skipped_no_comparable_score"`, and logs a user-friendly explanation that successful experiments existed but no comparable performance metric was available.

The finalizer will report a Paper Artifact Status instead of a raw boolean. `success` means TeX and PDF were generated; `partial` means `paper.tex` was preserved but PDF compilation still failed after repair attempts; `skipped` means generation conditions were not met; and `failed` means the paper module itself could not produce usable source artifacts. Logs must state the status in user-facing language and point to `paper_manifest.json` when it exists.

**Considered Options**

- Reuse `experiment_report.txt` as the final paper source. Rejected because it is a candidate-level factual report, not a launch-level scientific narrative.
- Reuse sci-task `report/report.md`. Rejected because that path belongs to paper reproduction and scoring, not new discovery output.
- Add a post-launch finalizer. Accepted because it is the smallest integration point that preserves existing workflow behavior.
