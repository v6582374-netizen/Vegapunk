Status: accepted

# Treat Tool Installations as Skill Sources

The direct Skill-content editing and Skill-deletion rules in this ADR are superseded by ADR 0172; the Skill-source, identity, applicability, and projection rules remain in force.
Project-scoped Skill directories and ProjectBinding state are outside the current Skill Management scope; a native Tool may still consume them without the manager discovering or managing them.

Skill Management will not require `~/.skills-manager/skills` to be the authoritative hub for every Skill.
Each configured Skill Tool Target remains a first-class Local Skill Source, and a Tool Skill Installation is considered applicable when its target contains readable Skill content, regardless of whether that content is a materialized directory or a symlink.

The manager may identify equivalent Skill installations and provide explicit synchronization actions, but it must not move every Skill into one central directory or use central ownership as the definition of tool availability.
Skill metadata lists only the Skill Tools that currently contain readable, callable installations; it does not list every Tool supported by the manager.
Installations are grouped into one Skill identity only when their declared identity and complete readable content agree; matching directory names alone do not merge divergent content.
Content divergence creates separate Skills rather than a merge conflict that the manager resolves automatically.
Edits target the resolved Skill Body.
When one Skill identity has multiple equivalent installations, the edit propagates to every replica, while a shared symlink target is updated only once.
Synchronized edits are all-or-nothing: the manager must preflight targets and roll back any partial write so a failed edit leaves every replica at its original content.
Known external Installation Provenance does not make the editor read-only: the user may edit the actual Skill Body, while the UI warns that the external installer or Tool may later overwrite local changes.
This transaction guarantee is scoped to the targets discovered and accepted by Skill Management; concurrent filesystem changes made outside the application are not modeled as a separate conflict workflow.
Installation form and symlink provenance are separate facts.
The UI may report evidence-based provenance such as npx skills, Skill Manager, Tool-native, or Unknown, together with the resolved target path, but it must not infer a historical creator when no registry or source metadata proves it.
Deleting a Skill identity removes only that identity's Skill Body replicas and symlink entries that resolve to those bodies, rather than treating a symlink entry as the primary object; a different-content Skill with the same directory name is not part of the deletion set.
When Installation Provenance identifies an installer-native removal route, Skill Management presents that command as the preferred cleanup path; a symlink's existence alone is not evidence that its target still exists.
All removal commands are Manual Removal Commands: Skill Management only renders or copies advisory text and never executes an external shell command, records deletion intent, or creates a pending state on the user's behalf.
The Delete Skill action is separate: after explicit confirmation, it may mutate the verified Skill Body and related symlink entries directly, while the advisory command remains available as the installer-native cleanup recommendation.
Skill deletion is also all-or-nothing across the verified Skill Body replicas and related symlink entries under configured Tool Skill Targets: if the application cannot complete the planned deletion set, it must fail the operation rather than intentionally accept a partial deletion.
Symlinks outside configured Tool Skill Targets are external references, not deletion targets; the manager may report them when it has evidence of them but does not perform a whole-filesystem search or delete them automatically.
When an external installer is known, direct deletion must warn that installer metadata may remain and present the installer-native Manual Removal Command as the cleaner alternative.
When provenance is unknown, the manager must not invent an installer command; it may show only verified path-based cleanup commands after checking the Skill Body's remaining references.
For a Skill with multiple installations, the deletion view presents one installer-native command per known Installation Provenance and separate verified path cleanup commands for residual symlink entries or unknown bodies.
Provenance records are evidence for explanation and command generation, not authority over current filesystem state; current state changes only when a later read-only rescan observes the filesystem.
Refresh is read-only discovery: it classifies existing Tool Skill Installations but does not move directories, create symlinks, import content, or rewrite targets.
When the user explicitly applies an existing Skill Body to another Tool, the manager creates a symlink to that body rather than offering a copy-versus-symlink choice.
The apply action is available only when the target is Off; an existing readable real directory or valid symlink already makes the Tool On, so it must not expose a second apply action.
If an Apply target path is occupied by a different-content real Skill, Apply fails without mutation; it must not rename, overwrite, or move the existing Skill to make room.
If an Apply target is a broken symlink, explicit Apply may replace that dangling link with a symlink to the current Skill Body; Refresh remains read-only and never performs this repair implicitly.
The per-Tool switch has projection semantics: for a Symlink Projection Tool, On to Off removes only the symlink, while a Body-Hosting Tool remains On with a disabled switch.
When a known Skill Body has no Body-Hosting Tool and no valid symlink projection, Skill Management retains the Skill in its inventory as not currently applied to any Tool; its Tool metadata is empty and every known Tool is Off.
Deleting the Skill identity remains the separate operation that removes the Skill Body and all related symlink entries.

## Consequences

- Tool applicability and filesystem materialization are modeled as separate facts.
- A symlink remains a valid installation form, but its target and ownership must be reported separately from applicability.
- Refresh must discover real Skill content without silently converting it into a central copy.
- Deletion must state which Tool Skill Installations it will affect and must not remove user-owned content merely because it is present under a configured tool path.
