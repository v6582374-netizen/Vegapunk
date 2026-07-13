---
status: accepted
---

# Refocus on the Terminal Candidate with One Final Sculptor Call

Immediately after Terminal Candidate Selection, InternAgent invokes the Manuscript Sculptor once with the exact in-memory selection result, the canonical TeX absolute path, and the Selected Research Candidate's authoritative artifact path. This is the only normal Sculptor Invocation that does not originate from an Agent Task Completion or Sculptor Context Fork, because candidate selection may be completed entirely by deterministic comparison or randomized fallback and therefore may have no source Agent session.

The invocation globally refocuses the accumulated Living Manuscript around the Selected Research Candidate. It aligns the title, abstract, claims, method, evidence, comparisons, limitations, Evidence Carriers, and conclusion; material from unselected candidates remains only when it serves a valid comparison, ablation, negative result, boundary, or explanation. The Sculptor does not reconstruct the research history from scratch because ordinary Agent Task hooks have already maintained the manuscript throughout Discovery.

After this invocation passes the normal deterministic validation and forward-repair contract, its validated files are the synchronized paper output and automatic writing stops under ADR-0069. InternAgent does not automatically invoke PaperOrchestra afterward.

**Considered Options**

- Do nothing after deterministic selection. Rejected because the manuscript could remain organized around several unresolved candidates after the system has already chosen one.
- Invent a selection Agent solely to obtain a context fork. Rejected because wrapping an authoritative deterministic decision in a model call adds no information and obscures the actual selection authority.
- Rebuild the paper from selected artifacts. Rejected because it discards the manuscript continuously sculpted from earlier Agent contexts.
