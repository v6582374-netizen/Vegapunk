---
status: accepted
---

# Selectable Discovery Experiment Backends

Status: Accepted  
Date: 2026-08-06

## Decision

Discovery supports three coding-agent backends: `codex`, `qwen_code`, and
`openhands`.

- A CLI Launch must receive an explicit `--exp_backend` value.
- A Web Launch reads the top-level `backend` field in Settings → Discovery
  Launch and copies the validated value into its immutable Launch snapshot.
- CLI and Web Launches are independent entry points. They never share a
  precedence rule or overwrite one another's backend choice.
- New Web Launches default to `codex`.
- Qwen Code uses the official installed CLI in unattended mode with
  `--approval-mode yolo`, JSON output, the selected model, and the private
  Launch workspace. It follows the existing Codex runner contract for
  iterations, `ALL_COMPLETED`, logs, artifact validation, and final messages.
- Removed legacy backend identities are closed-enum failures. They are not
  migrated or silently resumed through another backend.

## Consequences

Backend selection remains separate from Model Provider selection. Settings
changes affect only newly admitted Web Launches; running and resumed Launches
continue to use their captured snapshot. The shared experiment loop keeps
candidate results and MCTS behavior consistent while each coding-agent adapter
owns only its CLI invocation and output parsing.
