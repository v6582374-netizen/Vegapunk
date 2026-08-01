# 03 - Convert and save a reviewed Formatted Discovery Input revision

**What to build:** The Sole Researcher can explicitly convert a committed Discovery Preparation through the configured Discovery Input Conversion Prompt and global default model boundary, edit the result, and save an immutable Formatted Discovery Input revision without starting a Launch.

**Blocked by:** 02 - Commit one Discovery Preparation from file and text intake.

**Status:** completed

- [x] Conversion is available only for a non-empty valid Preparation and is never triggered by intake or Save.
- [x] Conversion uses the active Discovery Input Conversion Prompt and global default text model and parameters without adding a Discovery-local model picker.
- [x] PDF, DOCX, and ZIP readability errors are surfaced during Conversion while the underlying Source Entry remains deletable.
- [x] A successful conversion produces an editable Formatted Discovery Input Draft and does not mutate sources, research text, or Launch state.
- [x] An explicit Save of a non-empty Draft appends an immutable revision and preserves earlier revisions.
- [x] Editing a saved Draft creates an unsaved revision candidate and keeps Run unavailable until it is explicitly saved.
- [x] Changing source or text input after a saved revision marks the Preparation dirty and requires reconversion before Run.
- [x] Conversion failure or empty output creates no revision and leaves earlier saved revisions unchanged.
- [x] The Convert and Review stages expose accessible pending, editing, saved, dirty, and failed states in the Native GUI.
