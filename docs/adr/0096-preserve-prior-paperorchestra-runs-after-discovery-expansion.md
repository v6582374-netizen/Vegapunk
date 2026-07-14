---
status: accepted
---

# Preserve Prior PaperOrchestra Runs After Discovery Expansion

If a Discovery Launch has already completed Draft Handoff and the user later explicitly resumes it with additional configured Discovery work, the expanded Research Draft produces a new PaperOrchestra Run at the next handoff. The earlier PaperOrchestra Run, including its sources, figures, PDF, and checkpoints, remains unchanged; the later run consumes the Draft as expanded by the additional Discovery work.

This is not a separate version-management subsystem. It only prevents a later automatic handoff from overwriting a paper generated from an earlier research state. Re-entering PaperOrchestra for the same handoff still resumes that handoff's existing incomplete PaperOrchestra Run rather than creating another one.

**Considered Options**

- Overwrite the earlier PaperOrchestra Run. Rejected because it destroys the paper corresponding to the earlier completed research state and conflates resuming PaperOrchestra with expanding Discovery.
- Return the already completed paper after the Draft has expanded. Rejected because the paper would silently omit the newly appended research information.
