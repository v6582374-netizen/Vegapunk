---
status: superseded by ADR-0077
---

# Sculpt One Living Manuscript Throughout Discovery

Vegapunk will maintain one Living Manuscript throughout a Discovery Launch instead of waiting until discovery ends to begin writing. Before Terminal Candidate Selection, the manuscript is organized around the launch's stable research question and baseline rather than prematurely adopting a candidate; after selection, it undergoes a global rewrite and pruning pass centered on the Selected Research Candidate. Every Agent Task Completion invokes the Manuscript Sculptor against the latest manuscript through the Sculptor Context Fork; the sculptor alone decides whether the completed task warrants no manuscript change or some addition, removal, revision, or reorganization. Individual model calls, low-level tool operations, retries, and partial outputs inside an unfinished Agent task do not invoke it. The sculptor owns editorial inclusion and expression but cannot declare evidence valid, judge experiments, or select research candidates; those scientific decisions remain with discovery orchestration. Manuscript changes are serialized and accepted only after deterministic document validation. Once the final research outcome and Terminal Candidate Selection have been incorporated, the latest validated manuscript is the synchronized paper output and automatic writing processes stop; PaperOrchestra is optional under ADR-0069.

ADR-0060 governs the sculptor through an outcome-based completion criterion rather than enumerated edit modes or a mandatory-change workflow.

ADR-0070 transfers observable Agent context before it is discarded while retaining canonical absolute paths for the Living Manuscript and authoritative evidence.

ADR-0062 makes direct edits to those canonical manuscript files the sculptor's output; prose returned by the model is never a second manuscript representation.

ADR-0063 keeps a sculpting invocation active after validation failure so the same agent repairs the current files forward instead of rolling back valid editorial progress.

ADR-0065 makes the Manuscript Sculptor Prompt a mandatory injection before every writing action rather than a separately invoked skill, and ADR-0066 requires authoritative changes to propagate through every dependent part of the manuscript.

ADR-0067 keeps the repository-local ElegantPaper resources shared and read-only while each Discovery Launch owns exactly one editable manuscript source.

ADR-0068 permits the early Living Manuscript to remain rhetorically incomplete rather than filling unsupported sections or results.

ADR-0069 stops the normal workflow at the synchronized manuscript and leaves PaperOrchestra as an explicitly invoked future optimization path.

ADR-0071 removes upstream significance filtering and fixes Agent Task Completion as the universal manuscript-consideration boundary.

ADR-0076 adds one explicit non-Agent invocation after Terminal Candidate Selection so the accumulated manuscript is globally refocused around the selected winner before the synchronized output is finalized.

**Considered Options**

- Begin all writing after discovery. Rejected because the final handoff compresses and filters research context before the manuscript can use it.
- Add a separate research ledger, claim registry, and manuscript projection. Rejected because the existing research artifacts already retain factual outputs and the extra representations introduce additional synchronization and interpretation boundaries.
- Invoke a writer after every model or tool call. Rejected because transient implementation steps create excessive cost, manuscript churn, and noise without representing completed scientific work.
