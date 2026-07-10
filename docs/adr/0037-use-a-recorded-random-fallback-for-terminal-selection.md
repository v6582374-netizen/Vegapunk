---
status: accepted
---

# Use a Recorded Random Fallback for Terminal Selection

Terminal Candidate Selection first follows the accepted direct and metric-based path: use the sole successful candidate when only one exists; otherwise use the explicit or terminally inferred primary metric and direction, exclude candidates without a finite comparable value when comparable candidates remain, and select a unique optimum. If that path cannot produce exactly one candidate for any reason, PaperOrchestra stops adding special-case decision branches and randomly selects from the relevant successful fallback pool.

The fallback never includes a failed Candidate Experiment. An exact metric tie uses the tied optimum set under ADR-0036; when no valid comparison or criterion exists, the fallback pool is all successful candidates in the Paper Candidate Round. Before writing begins, the Dossier Run persists the triggering condition, complete fallback pool, random-selection method, and selected candidate. Resuming the same Dossier Run reuses that result.

Every randomized fallback is mandatory Candidate Selection Provenance. The Research Narrative states the condition that prevented a unique evidence-based choice and explicitly states that the final paper subject was selected randomly. This closes the deferred selection mechanism in ADR-0023 and supersedes the provisional edge-case proposal in ADR-0034.

**Considered Options**

- Add a dedicated recovery rule for every future selection anomaly. Rejected because the initial migration prioritizes a simple, terminating pipeline over speculative branching.
- Hide random fallback from the paper. Rejected because readers must be able to distinguish measured superiority from an operational selection fallback.
