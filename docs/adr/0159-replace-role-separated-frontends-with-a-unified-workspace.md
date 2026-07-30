Status: superseded by the Desktop-first product direction

> Historical ADR. The browser-based Unified Workspace described here was the retired root Web frontend. The active product UI is now the OpenWorker Desktop App.

# Replace role-separated frontends with a unified workspace

Vegapunk will replace its separate researcher and administrator browser surfaces with one local Unified Workspace.
The workspace has no sign-in, administrator routes, or role-specific navigation, and organizes all capability areas under a persistent sidebar with a central work area and optional Artifact Preview.
This deliberately makes the Version 1 local, sole-researcher boundary the only access boundary; remote or multi-user deployment requires a new identity and authorization decision.
