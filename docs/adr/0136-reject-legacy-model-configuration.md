# Reject Legacy Model Configuration

The unified configuration schema will not accept the former Provider/model fields or compatibility aliases after migration.
Legacy fields such as `default_provider`, caller-local `model_name`, role-specific text model settings, and `model_aliases` will produce an explicit configuration error instead of being ignored or translated.

## Consequences

- Every shipped configuration must be migrated before the unified runtime is usable.
- Configuration errors are detected before any model request is made.
- Backward compatibility is provided by a deliberate migration of files, not by retaining a second runtime configuration path.
