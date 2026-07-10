---
status: accepted
---

# Isolate PaperOrchestra Configuration

The port adds `config/paper_orchestra.yaml` for settings owned only by the writing subsystem. Its initial configurable surface is `enabled`, `template_dir`, `layout_review_enabled`, `max_content_refinement_iterations`, and `max_format_correction_iterations`; the accepted defaults are enabled Dossier generation, ElegantPaper, enabled multimodal layout review, three content-refinement iterations, and one formatting-correction iteration.

The file does not duplicate provider, model, endpoint, credential, or API-key settings. The Dossier Service receives the model created through InternAgent's existing configuration and `ModelFactory`. `launch_discovery.py` loads the fixed default PaperOrchestra configuration path, while the standalone historical-run command may explicitly override that path.

Stable runtime contracts such as the `primary` Dossier Run ID, stage order, checkpoint semantics, and final output filenames are not configurable in the initial integration.

**Considered Options**

- Add PaperOrchestra settings to `config/default_config.yaml`. Rejected because writing configuration can remain additive and isolated from InternAgent's existing configuration contract.
- Duplicate model configuration in the new file. Rejected because PaperOrchestra must use the same unified model instance as InternAgent rather than create a second provider path.
