---
status: accepted
---

# Constrain the Sculptor by Outcome, Not Edit Modes

The Manuscript Sculptor Prompt will not classify an invocation into predefined editing modes, prescribe a sequence of local and global operations, require an edit plan, or require every invocation to change the Living Manuscript. The model chooses its own editing strategy and granularity from the current manuscript and supplied authoritative information; adding, deleting, rewriting, reorganizing, or making no change are ordinary editorial judgments rather than workflow states.

The prompt has one core completion criterion: continue editing until the Living Manuscript is the most coherent, publication-oriented scientific argument that the currently supplied evidence can support. Every retained claim, citation, and Evidence Carrier must remain mutually consistent and evidence-grounded; obsolete, contradicted, redundant, or exploration-specific material must not survive merely because it already exists. Under ADR-0064, Argument Density determines whether otherwise factual content belongs; ADR-0066 requires changed conclusions to propagate through the full manuscript; ADR-0068 permits unsupported responsibilities and sections to remain absent during early research. Completion may legitimately produce no file change when the new outcome does not improve that state.

This refines ADR-0050 without adding an edit-mode field, state machine, planning artifact, or orchestration branch. Deterministic validators continue to check document integrity, while the dedicated prompt supplies the editorial quality bar that cannot be reduced to mechanical checks.

**Considered Options**

- Define `NO_CHANGE`, `LOCAL_REVISION`, and `GLOBAL_RESCULPT` modes. Rejected because a capable model can infer edit scope directly and the classification duplicates its editorial judgment.
- Always rewrite the whole manuscript. Rejected because irrelevant or localized outcomes do not justify unnecessary drift.
- Require every invocation to produce a patch. Rejected because restraint is a valid editorial decision when the manuscript already reflects the supplied information.
