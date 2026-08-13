# 原型化符合 OpenWorker 视觉语言的 Prompt 库设置模块

Type: prototype
Status: open
Assignee: Claude
Labels: wayfinder:prototype
Parent: ../map.md
Blocked by: 09-define-core-prompt-library-module-contract.md
Blocks: 12-define-prompt-library-acceptance-and-regression-gates.md

## Prototype asset

- [OpenWorker Prompt Library throwaway prototype](../prototypes/prompt-library/README.md)
- Run: `bash .scratch/openworker-macos-desktop-reuse/prototypes/prompt-library/run.sh`
- Compare: `A — Catalogue + editor`, `B — Browse then focus`, and `C — Workflow navigator`
- Use the prototype-only state picker to inspect ready, loading, unavailable, invalid, saving, and saved states.

## Review prompt

Which composition should define the V1 module, and which elements should be borrowed from the other variants? In particular, compare catalogue scanability, editing focus, workflow/stage orientation, metadata density, save-state clarity, and how disruptive the unavailable-service state feels.

## Question

What concrete settings navigation, catalogue, search, metadata presentation, editor, validation feedback, save state, loading state, and unavailable-service state make the core Prompt Library feel native to OpenWorker rather than transplanted from Vegapunk's current Web Workspace?
The prototype must reuse OpenWorker's existing layout, components, typography, spacing, colors, motion, dialogs, and interaction conventions rather than copying the current Vegapunk Prompt Library UI.
