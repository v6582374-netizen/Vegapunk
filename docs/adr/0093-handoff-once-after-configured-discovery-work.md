---
status: accepted
---

# Handoff Once After Configured Discovery Work

Automatic Draft Handoff occurs only after all rounds, Agent tasks, and Experiment Runs requested by the current Discovery configuration have reached terminal outcomes and their final events have been appended. PaperOrchestra does not consume a Draft that Discovery is still extending. An interrupted core workflow resumes its own work first and reaches handoff later; interruption itself does not force a partial automatic handoff.
