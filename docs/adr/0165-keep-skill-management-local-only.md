Status: accepted

# Keep Skill Management Local-Only

The in-scope feature list in this historical ADR is narrowed by ADR 0172; current Skill Management excludes Skill creation, editing, import/export, deletion, usage monitoring, risk scanning, translation, and other AI analysis.

The imported Skill Management module exists to manage the Sole Researcher's local Skills and their projections into local Skill Tool Targets.
Remote Marketplace browsing, remote source configuration, remote Skill installation and update flows, Marketplace metadata snapshots, and Marketplace community interactions are out of scope and will be removed.
The imported Feedback page, remote webhook submission, group QR-code entry points, and GitHub issue shortcut are also out of scope for the local module.
Application update checks and installation are Desktop App lifecycle services and are not exposed by Skill Management.
Marketplace-specific GitHub tokens and remote-source authorization are also out of scope once the remote catalog is removed.
Upstream project branding, privacy links, donation assets, and support links are likewise not part of the integrated local module.
Previously installed remote or vault Skills remain Installed Local Skills, with their files and local tool projections preserved while obsolete remote metadata is ignored or migrated away.

## Consequences

- Skill Management has no remote catalog, remote Skill identity, or remote installation dependency.
- Local Skill creation, editing, import/export, tags, favorites, risk scanning, translation, usage monitoring, and tool synchronization remain in scope.
- Remote Marketplace code and account-facing copy must not be reintroduced as a prerequisite for local Skill management.
- Support and feedback submission belong to a future Desktop App support surface or an external workflow, not to local Skill management.
- Application updates have one Desktop App owner and do not appear as Skill Management actions.
- Skill Management does not store or request a GitHub credential for remote catalog access.
- About, privacy, and support navigation is owned by the Desktop App when it exists, with no inherited upstream links.
- Removing remote features is non-destructive for existing local Skill files and projections.
- Configuration migration removes remote residues without requiring a manual account cleanup step.
