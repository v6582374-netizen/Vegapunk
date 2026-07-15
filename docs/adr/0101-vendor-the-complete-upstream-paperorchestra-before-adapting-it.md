---
status: accepted
---

# Vendor the Complete Upstream PaperOrchestra Before Adapting It

InternAgent will replace the independently rewritten `internagent.paper_orchestra` implementation from a complete source copy of upstream PaperOrchestra, initially pinned to commit `ca1b3fa01c2970fc7cda32d16245db38d57b3f56`. Every file tracked by that upstream commit is imported under `third_party/paper_orchestra/` as a vendored subtree without a nested `.git` directory. The copied source tree, control flow, prompts, roles, and default behavior are the implementation baseline; local changes are limited to adaptations required for integration with InternAgent. This prioritizes reproducing upstream behavior and paper-generation effects while making every local divergence directly reviewable.

The upstream import is recorded as a source-only baseline change before any adaptation. Model integration, input and output bridging, runtime coordination, and every other adaptation follow in separate reviewable changes; the import may then be modified in place rather than treated as an immutable mirror. `internagent.paper_orchestra` remains the outer InternAgent integration boundary instead of containing another rewrite of upstream agents. The current implementation stays available as comparison evidence until the replacement path passes its migration acceptance checks.

This decision supersedes ADR-0015's selective internal port. Existing decisions about the model runtime, asynchronous execution, checkpoints, resume behavior, input materials, and safety checks must now be re-evaluated individually against the source-faithful baseline instead of being assumed as constraints on a rewritten core. The current implementation and its tests remain evidence of InternAgent requirements, but they are not the source baseline for the replacement.

**Considered Options**

- Continue maintaining the current native rewrite and recover upstream behavior through parity fixes. Rejected because its low source similarity and reorganized control flow make behavioral omissions difficult to identify and risk independently recreating mechanisms already present upstream.
- Copy only the currently selected upstream runtime files. Rejected because omitted entrypoints, utilities, or supporting paths may participate in the original behavior, and the intended strategy is to begin from the complete upstream project before minimizing integration changes.
- Overlay the upstream tree onto the InternAgent repository root. Rejected because both projects own root-level files and package names, which would erase the source boundary and create ambiguous configuration and dependency ownership.
- Keep PaperOrchestra as a Git submodule. Rejected because the replacement source and its local adaptations must be present and reviewable in the InternAgent repository rather than stored as state belonging to a second repository.
