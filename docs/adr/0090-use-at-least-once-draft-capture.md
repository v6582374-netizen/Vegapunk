---
status: superseded by ADR-0110
---

# Use At-Least-Once Draft Capture

Research Draft capture has no independent checkpoint, cursor, replay detector, or deduplication layer. For a core operation that persists a checkpoint, its Observable Research Event is appended before the core checkpoint is committed. An interruption between those actions may cause the core to replay the operation and append a duplicate Draft Block, which is preferable to checkpointing the operation while permanently omitting its research information. PaperOrchestra must tolerate duplicate raw material.
