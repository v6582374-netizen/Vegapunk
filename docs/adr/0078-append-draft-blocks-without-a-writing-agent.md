---
status: superseded by ADR-0110
---

# Append Draft Blocks Without a Writing Agent

Research Draft capture is deterministic infrastructure, not an authoring role. Each Observable Research Event is appended directly to `manuscript/draft.md` with no model, writing Agent, subagent, prompt, editorial judgment, metadata, filtering, redaction, or content transformation. Text and structured payloads are preserved in full, and mathematical expressions are recorded verbatim with their notation, delimiters, definitions, assumptions, and derivation steps so downstream paper construction cannot lose formulas. A fixed non-rendered delimiter is the only structural addition between raw event contents.

This supersedes the Manuscript Sculptor, Sculptor Context Fork, Sculptor Invocation, Sculptor Completion Barrier, and Sculptor-Capable Agent Runtime concepts. PaperOrchestra alone owns downstream interpretation, filtering, organization, and paper writing.
