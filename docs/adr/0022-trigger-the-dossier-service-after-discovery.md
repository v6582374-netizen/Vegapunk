---
status: accepted
---

# Trigger the Dossier Service after Discovery

After `launch_discovery.py` has completed the Discovery Launch and written `discovery_summary.json`, it will invoke the single Dossier Service entrypoint so the research-to-writing flow remains continuous. This is the one accepted modification to the existing discovery entrypoint; it does not authorize changes to Candidate Experiment production, and Dossier failure remains isolated from Discovery success as defined in ADR-0002.

The trigger decision is independent of paper-candidate selection. Its final handoff payload must not assume that a Selected Research Candidate has already been determined until that mechanism is designed separately. This supersedes ADR-0020, which prematurely required the discovery entrypoint to pass a concrete selected-candidate directory.

**Considered Options**

- Require a person to start every Dossier Run after Discovery finishes. Rejected because it breaks the intended end-to-end workflow.
- Let discovery coordinate individual PaperOrchestra agents. Rejected because the Dossier Service remains the single boundary around the writing subsystem.
