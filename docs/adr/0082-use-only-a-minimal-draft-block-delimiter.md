---
status: accepted
---

# Use Only a Minimal Draft Block Delimiter

Research Draft blocks contain no semantic metadata, event labels, timestamps, identifiers, status fields, or editorial envelope. Capture appends the raw observable event content in physical arrival order under an atomic append lock and places only the fixed non-rendered Markdown delimiter `<!-- draft-block -->` between adjacent blocks. This preserves the user's raw-material requirement while keeping block boundaries recoverable without inventing meaning.

Delimiter collision escaping is intentionally deferred. The expected collision rate is low for current machine-generated payloads, and introducing an escaping or side-index protocol now would add complexity before evidence shows it is needed.
