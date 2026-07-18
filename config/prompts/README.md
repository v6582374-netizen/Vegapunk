# Prompt Library

Disk-backed registry of editable prompts (ADR-0156 / ADR-0157).

## Layout

- `catalog.yaml` - index: `id`, `name`, `description`, `stage`, `file`
- `<stage>/<name>.txt` - prompt body (may use `{placeholders}` for `.format`)

## Add a prompt

1. Write the text file under the right stage directory.
2. Append an entry to `catalog.yaml`.
3. Read it with `from internagent.prompt_library import prompts` then
   `prompts.get("your.id")` or `prompts.render("your.id", key=value)`.
4. Prefer call-time `get`/`render` over import-time string constants so a
   Launch Configuration Snapshot can override the root.

## Stages

- `experiment` - experiment-backend coder / debug prompts
- `discovery` - MAS idea/method/codeview system prompts
- `deep_research` - DR planner/coordinator/section/tool prompts
- `paper` - PaperOrchestra / autorater prompts
- `scoring` - Sci evaluation prompts

## Exemptions

See `exemptions.yaml` for patterns still allowed to keep inline strings
(CAMEL vendored unused paths, dynamic user-prompt assembly, some PDF utils).
The coverage test in `tests/admin_console/test_prompt_externalization_coverage.py`
enforces this list.
