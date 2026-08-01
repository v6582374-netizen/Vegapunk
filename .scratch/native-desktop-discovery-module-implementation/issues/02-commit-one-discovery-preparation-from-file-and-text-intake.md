# 02 - Commit one Discovery Preparation from file and text intake

**What to build:** The Sole Researcher can assemble one Native Desktop Discovery Preparation from free-form text and multiple individually uploaded files, review accepted Source Entries, explicitly save the whole Preparation, and recover the latest committed state after restart.

**Blocked by:** 01 - Establish the Native Discovery shell and sidecar route seam.

**Status:** completed

- [x] Preparation accepts free-form text and multiple individual files in one intake flow.
- [x] The file picker and API reject folders and accept only `.txt`, `.md`, `.pdf`, `.docx`, `.csv`, and `.zip` files.
- [x] Empty files, invalid identities, incomplete bytes, and invalid multi-file batches are rejected without creating partial Source Entries.
- [x] Each accepted Source Entry has a stable identity and supports add and delete operations without a Replace operation.
- [x] The GUI keeps source and text edits in a Draft until one explicit whole-Preparation Save succeeds.
- [x] A failed Save preserves the previous committed state, while an explicitly saved empty Preparation clears the current input.
- [x] Restart restores only the latest committed Preparation and discards unsaved Draft changes.
- [x] The Gather stage exposes accessible empty, draft, saved, validation-error, and reset states through the Native GUI.
