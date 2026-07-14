---
status: accepted
---

# Automatically Run PaperOrchestra from the Research Draft

After Discovery finishes appending Observable Research Events, InternAgent automatically starts PaperOrchestra with the launch-local `manuscript/draft.md` as its non-structured source material. Discovery does not claim that the Draft is a paper; PaperOrchestra owns interpretation, selection, organization, figure planning, LaTeX writing, refinement, and delivery of the complete paper artifact. A Launch therefore does not stop at the Draft when a complete paper is required.

Draft capture stops at the one-way handoff. The Research Draft remains append-only and is never read-and-extended or rewritten by PaperOrchestra; PaperOrchestra model calls, tools, outline work, figure generation, section writing, review, and compilation are persisted only in its own run artifacts and checkpoints. Handoff supplies the Draft's absolute path, the Discovery Launch root, and an optional candidate-selection path without first rendering a selected-candidate `raw_materials/` bundle. PaperOrchestra may read authoritative launch artifacts, but how it uses and internally organizes them belongs to its own orchestration logic.

The combined workflow has no global binary success or failure verdict. Its state is the set of persisted research artifacts, Draft Blocks, PaperOrchestra stage outputs, and checkpoints available for continuation.

Terminal Candidate Selection is optional context rather than a handoff gate. PaperOrchestra starts whether or not Discovery produced a Selected Research Candidate and must limit its claims to the evidence actually present.
