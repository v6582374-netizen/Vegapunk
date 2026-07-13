---
status: superseded by ADR-0069
---

# Trigger Dossier Generation by Default

After a normal Discovery Launch completion writes `discovery_summary.json`, `launch_discovery.py` will trigger the Dossier Service by default. An explicit disable setting owned by the new PaperOrchestra subsystem may skip this stage for experiment-only or diagnostic runs; the integration will not add this setting to InternAgent's existing `default_config.yaml`.

Dossier failure remains isolated from Discovery success. This supersedes ADR-0002's default-disabled, opt-in behavior because the standard project workflow is now intended to continue from discovery through Research Dossier generation without requiring an additional manual action.

**Considered Options**

- Keep Dossier generation disabled by default. Rejected because the standard launch would still stop before completing the research-to-writing loop.
- Make Dossier generation impossible to disable. Rejected because experiment-only and diagnostic runs should not be forced to pay writing and compilation costs.
