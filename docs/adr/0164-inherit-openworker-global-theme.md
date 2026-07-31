Status: accepted

# Make Skills Manager Inherit the OpenWorker Global Theme

Skill Management will inherit the OpenWorker Global Theme Contract across Skills, Tools, Editor, Settings, and Welcome.
It will use the root document theme state, shared surface tokens, and shared font stack instead of maintaining a separate `.skills-manager-root` light/dark theme implementation or font override.

## Consequences

- Background, card, border, foreground, and semantic signal colors remain visually consistent with the rest of OpenWorker.
- Theme changes apply to Skills Manager without a second preference or a module-specific dark-mode lifecycle.
- The Desktop App Settings surface is the sole theme preference owner; Skills Manager Settings does not expose a second theme selector.
- The OpenWorker font stack is the sole font owner; Skills Manager Settings does not expose a font selector or font override.
- Skills Manager's upstream copy remains available for provenance, while the integrated surface owns the theme adaptation.
