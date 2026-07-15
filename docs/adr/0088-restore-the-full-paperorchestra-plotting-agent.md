---
status: superseded by ADR-0101
---

# Restore the Full PaperOrchestra Plotting Agent

The InternAgent adaptation will restore PaperOrchestra's full Plotting Agent rather than limiting figures to existing files copied from Experiment Runs. The restored workflow includes figure planning, statistical and result plots, method and architecture diagrams, image generation where supported, visual critique, and iterative correction. Existing authoritative figures remain reusable inputs; generated figures supplement them instead of forcing replacement.

Figure planning remains part of PaperOrchestra's scientific argument construction and has no fixed figure quota. Statistical plots must be traceable to recorded data and may not invent measurements, while explanatory method diagrams may visualize established concepts from the Research Draft and authoritative artifacts. Plotting Agent outputs, captions, and generation provenance belong to the PaperOrchestra Run, never to the append-only Research Draft.

This supersedes the earlier decision to omit the upstream Plotting Agent and the assumption that one general writing role should deterministically render every missing carrier itself.
