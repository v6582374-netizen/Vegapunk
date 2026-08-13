# OpenWorker Prompt Library — throwaway UI prototype

> Three variants of the Prompt Library settings module, switchable via `?variant=A|B|C`, in OpenWorker's existing full-page Settings shell.

This is a **throwaway prototype**, not production implementation. It uses in-memory sample data and no real Vegapunk API mutations.

## Run

```bash
bash .scratch/openworker-macos-desktop-reuse/prototypes/prompt-library/run.sh
```

Open <http://127.0.0.1:4174/?variant=A>.

## What to evaluate

- **A — Catalogue + editor:** persistent two-column master/detail workspace.
- **B — Browse then focus:** calm catalogue first; editing moves into a focused detail layer.
- **C — Workflow navigator:** stage-driven navigation with a compact prompt queue and wide editor.

Use the prototype bar to switch variants and representative states: ready, loading, unavailable, invalid, saving, and saved. Editing the Prompt body, changing selection, resetting, and saving are simulated in memory.
