---
status: superseded by ADR-0069
---

# Wait for the Dossier Run to Finish

After triggering the Dossier Service, `launch_discovery.py` will wait synchronously until the Dossier Run reaches a success or failure terminal state. The discovery command therefore does not report overall completion while PaperOrchestra is still running in an unowned background process, and callers can inspect the recorded Dossier status and final output path as soon as the command returns.

A failed Dossier Run is recorded and returned by the service but does not change a successfully completed Discovery Launch into a discovery failure. The integration will not daemonize, detach, or otherwise launch PaperOrchestra as a fire-and-forget task.

**Considered Options**

- Start PaperOrchestra in the background and let discovery exit immediately. Rejected because process lifetime, logs, terminal status, and final-PDF availability would become ambiguous.
- Treat a Dossier failure as a Discovery failure. Rejected because the experiment evidence remains valid even when writing or LaTeX compilation fails.
