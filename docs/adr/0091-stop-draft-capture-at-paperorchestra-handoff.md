---
status: accepted
---

# Stop Draft Capture at PaperOrchestra Handoff

Research Draft capture covers Discovery only. Handoff occurs once after every currently configured Discovery round, Agent task, and Experiment Run has reached a terminal outcome and the last Observable Research Event has been appended. Capture then stops and the existing `manuscript/draft.md` becomes stable PaperOrchestra input. PaperOrchestra does not begin early while Discovery is still mutating the Draft; its model calls, tools, outlines, generated figures, paper sections, reviews, and compilation events belong to its own checkpointed run directory and never append back into the Research Draft.
