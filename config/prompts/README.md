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

## Stages in this slice (#7)

- `experiment` - former `internagent/prompts.py` bodies
- `discovery` - MAS idea/method agent system prompts

Later slices add Deep Research, vendored, paper, and scoring prompts the
same way.
