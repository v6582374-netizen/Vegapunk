---
status: accepted
---

# Isolate PaperOrchestra Configuration

The port adds `config/paper_orchestra.yaml` for settings owned only by the writing subsystem. Its configurable surface includes the shared template path, Draft batch size, Plotting Agent critique rounds, image-generation provider coordinates, layout review, content-refinement iterations, and formatting-correction iterations. PaperOrchestra is mandatory after Draft Handoff, so the configuration has no enable/disable switch.

The file does not duplicate the primary text provider, model, or credential settings. PaperOrchestra receives that model through InternAgent's existing configuration and `ModelFactory`; ADR-0097 defines the separate image-only provider and environment variable. `launch_discovery.py` loads the fixed default PaperOrchestra configuration path, while a standalone historical-run command may explicitly override that path.

Stable runtime contracts such as round-derived Run IDs, stage order, checkpoint semantics, and final output filenames are not configurable.

**Considered Options**

- Add PaperOrchestra settings to `config/default_config.yaml`. Rejected because writing configuration can remain additive and isolated from InternAgent's existing configuration contract.
- Duplicate model configuration in the new file. Rejected because PaperOrchestra must use the same unified model instance as InternAgent rather than create a second provider path.
