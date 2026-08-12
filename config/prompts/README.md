# Prompt Library

Disk-backed registry of editable prompts consumed by Vegapunk runtime code and the Native Desktop sidecar.

## Layout

- `catalog.yaml` - index: `id`, `name`, `description`, `stage`, `file`
- `<stage>/<name>.txt` - prompt body (may use `{placeholders}` for `.format`)

## Add a prompt

1. Write the text file under the right stage directory.
2. Append an entry to `catalog.yaml`.
3. Read it with `from vegapunk.prompt_library import prompts` then
   `prompts.get("your.id")` or `prompts.render("your.id", key=value)`.
4. Prefer call-time `get`/`render` over import-time string constants so a Launch Configuration Snapshot can override the root.

## Stages

- `experiment` - experiment-backend coder / debug prompts
- `discovery` - MAS idea/method/codeview system prompts
- `external_data` - Connector and Web Evidence acquisition prompts
- `deep_research` - DR planner/coordinator/section/tool prompts
- `paper` - PaperOrchestra / autorater prompts
- `scoring` - Sci evaluation prompts

## Exemptions

See `exemptions.yaml` for patterns still allowed to keep inline strings
(CAMEL vendored unused paths, dynamic user-prompt assembly, some PDF utils).
The coverage test in `tests/test_prompt_externalization_coverage.py` enforces this list.

Native Desktop Settings accesses the editable bodies through the local `openworker-server` sidecar at `/v1/prompt-library/*`.
The GUI does not start a separate HTTP API service.
