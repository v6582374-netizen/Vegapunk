Status: accepted

# Align Skill Management Language with the Desktop Surface

Skill Management will not expose or persist its own English/Chinese language selector.
Its static interface copy uses the current Desktop language contract, which is currently the Desktop's single English presentation.
The language used for local Skill content translation remains an analysis capability input and is not a UI preference.

## Consequences

- Welcome and Settings no longer render a language control.
- Skill Management configuration no longer owns a `language` preference or language migration path.
- The integrated module cannot drift from the Desktop's external language presentation.
- Local Skill translation keeps an explicit target language at the operation boundary rather than coupling content translation to UI chrome.
- The complete upstream copy remains unchanged for provenance and future comparison.
