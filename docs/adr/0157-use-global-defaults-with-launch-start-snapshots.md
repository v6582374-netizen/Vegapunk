Status: accepted

# Use Global Defaults with Launch-Start Snapshots

Prompts and run parameters exist only as service-wide global defaults: the Prompt Library and the Run Parameter Registry, stored as plain files that remain the single source of truth.
A Discovery Launch captures the complete effective configuration into its own results directory as the Launch Configuration Snapshot at start; the Launch reads only that snapshot.
Edits made through the Admin Console affect Launches that start afterwards, never a running Launch, and there are no per-Launch overrides or mid-run edits.
A Launch Resume continues from Workflow Progress checkpoints using exactly its original snapshot and never absorbs Prompt Library or Run Parameter Registry edits made after its original start, so one Launch's results are always explained by one configuration.
The Library keeps no built-in edit history; traceability comes from the per-Launch snapshots, and the developer's ordinary git workflow covers the files when history is wanted.

**Considered Options**

- Per-Launch prompt and parameter overrides edited at submission time. Rejected because the global-only model is simpler and the developer can edit globals immediately before enqueueing to the serial Launch Queue with the same effect.
- Mid-run editing of later rounds. Rejected because it conflicts with PromptEvolver's runtime evolution and makes one Launch's record a mix of configurations that cannot be audited.
- Resume that absorbs post-start edits. Rejected because a resumed Launch would silently combine two configurations in one experiment record.
- Database-backed configuration with version tables. Rejected because it removes prompts from the filesystem where the developer's search and git tooling operates, for history the snapshots already provide.

## Consequences

- Testing a configuration change against a Launch that is already running requires stopping it and starting a new Launch; the aborted Launch can only continue as it was.
- PromptEvolver's runtime evolution is a derivation recorded on top of the snapshot, not a write-back into the Prompt Library.
- The snapshot mechanism is mandatory infrastructure: no Launch may start without persisting its complete effective configuration.
