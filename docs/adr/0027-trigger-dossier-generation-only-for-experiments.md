---
status: superseded by ADR-0069
---

# Trigger Dossier Generation Only for Experiments

The automatic post-discovery Dossier trigger applies only when `launch_discovery.py` runs in `experiment` mode. `report` mode continues to generate its existing idea reports and then exits without creating a Dossier Run, because it does not execute Candidate Experiments or produce the measured run artifacts needed to support a publication-oriented scientific argument.

The Dossier Service must not compensate for a report-only launch by inferring missing experimental evidence or asking writing agents to turn untested ideas into experimental claims.

**Considered Options**

- Trigger PaperOrchestra after both modes. Rejected because report-only output lacks the experimental evidence required by the accepted Research Dossier contract.
- Add a reduced paper type for report mode. Rejected from the initial migration because it would introduce a second narrative contract before the complete experimental path runs end to end.
