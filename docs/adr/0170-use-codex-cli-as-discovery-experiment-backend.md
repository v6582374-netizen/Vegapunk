---
status: superseded by ADR-0183
---

# Use Codex CLI as the Initial Discovery Experiment Backend

This ADR records the initial Codex-only decision. ADR-0183 later makes the
coding-agent backend selectable while retaining Codex as the default.
The existing Discovery orchestration, workspace, launcher, artifact, metric, and retry contracts remain unchanged.
Claude Code is not retained as a hidden fallback for Discovery, while unrelated third-party or non-Discovery Claude integrations remain outside this decision.

## Permission mapping

Codex runs with `--sandbox workspace-write`, so the coding agent can read, write, and execute within the selected experiment workspace.
The runner passes `-c approval_policy=never`, which removes interactive approval prompts for the already-scoped workspace execution.
The runner passes `-c sandbox_workspace_write.network_access=true`, so network access is enabled without a domain allowlist.
The runner passes `--skip-git-repo-check` because MCTS can create a temporary experiment directory that is not itself a Git repository.
The runner does not grant access to files outside the selected workspace.

## Output mapping

Each invocation uses `codex exec --json`.
Codex JSONL events from stdout, stderr, and the process return code are recorded as the raw research event stream.
The runner also passes `--output-last-message <workspace-temporary-file>` and reads that file after a successful process exit.
The contents of the final-message file are returned as the existing runner string result consumed by the Discovery loop.
The JSONL event stream is therefore observability data, while the final-message file is the stable application response boundary.

This preserves the previous backend boundary without making the Discovery orchestrator parse Codex events or changing experiment completion markers such as `ALL_COMPLETED`.
