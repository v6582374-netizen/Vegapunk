---
status: accepted
---

# Keep Web as a Discovery Start Adapter

The Web implementation owns Preparation validation, immutable Launch Snapshot creation, and starting the existing production Discovery launcher. After admission, the existing Discovery, Experiment, PaperOrchestra, model, and artifact logic remains authoritative; Web adds observation and presentation but does not reimplement or steer the running workflow.

**Considered Options**

- Rebuild Discovery stages inside the Web backend. Rejected because it would duplicate and gradually diverge from the production runtime.
- Let the frontend orchestrate rounds or PaperOrchestra calls. Rejected because browser state is not durable execution state and would make the running workflow dependent on an open page.
