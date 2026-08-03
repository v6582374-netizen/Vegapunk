---
status: accepted
---

# Preserve the Web Discovery Observation Contract

The Web keeps its existing Discovery API and Preparation, Current Launch, History, log, and artifact views. The real `launch_discovery.py` execution replaces only the fake data source; its process outcome, logs, and persisted artifacts are projected into the existing observation contract, while the browser never controls intermediate Discovery or PaperOrchestra stages.

This keeps the Web change focused on starting and observing the real workflow rather than creating a second UI state machine or changing the production execution logic.
