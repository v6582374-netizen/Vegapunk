---
status: accepted
---

# Append to the Existing Draft on Resume

Research Draft initialization is launch-local and append-only. A new Launch creates an empty `manuscript/draft.md`; resuming that same Launch reopens the existing file and appends new raw blocks at its end. The Draft owns no checkpoint or resume cursor: core Discovery and PaperOrchestra checkpoints decide what work resumes, and any replayed observable events append again. Capture never truncates, rewrites, deduplicates, or reorders prior content.
