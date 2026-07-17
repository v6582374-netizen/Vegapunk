# Delete Project-Owned Legacy Provider Code

After the unified runtime migration, project-owned adapters, Deep Research model classes, Provider-specific dispatch branches, tests, and configuration for removed Providers will be deleted rather than left as dormant compatibility code.
Vendored third-party Provider implementations may remain physically present when they are outside the active project surface, but no project entry point may resolve them.

## Consequences

- The supported Provider surface is visible from the Catalog and active runtime rather than from historical files.
- Reintroducing a removed Provider requires a new integration and capability declaration.
- Cleanup must distinguish project-owned code from vendored source to avoid accidental upstream rewrites.
