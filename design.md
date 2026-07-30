# Design - Vegapunk

This is the locked visual system for the Desktop App workspace.
Future visual work must extend this system intentionally instead of introducing a second identity language.

## Genre

Modern-minimal research workbench.

## Macrostructure family

- App modules: Workbench Field with a persistent module rail and a central work area.
- Exhibition Module: Project Space may use a stronger Material Expression Layer around research context and outputs.
- Operational modules: configuration and dense records stay quiet and prioritize readability.

## Theme

- Foundation: Rice-White Workspace.
- Identity tone: one low-saturation tea-gold Unified Tonal Spectrum.
- Material vocabulary: Maki-e Research Expression through controlled powder aggregation, sparse links, local texture, and blank space.
- Exclusions: no dark lacquer shell, historical motifs, second named art direction, rainbow spectrum, or particle-based telemetry.

## Canonical tokens

The Desktop App's visual tokens are maintained in its own GUI source tree. The legacy root `frontend/tokens.css` file is no longer an active source of truth.

```css
:root {
  --color-paper: oklch(97.5% 0.012 82);
  --color-paper-2: oklch(95% 0.016 82);
  --color-paper-3: oklch(91.5% 0.022 82);
  --color-ink: oklch(20% 0.018 72);
  --color-rule: oklch(82% 0.022 82);
  --color-accent: oklch(61% 0.13 78);
  --color-accent-ink: oklch(20% 0.018 72);
  --color-focus: oklch(46% 0.158 74);
  --font-display: "Space Grotesk Variable", "PingFang SC", "Hiragino Sans GB", sans-serif;
  --font-body: "IBM Plex Sans Variable", "PingFang SC", "Hiragino Sans GB", sans-serif;
  --font-mono: "IBM Plex Mono", "SFMono-Regular", monospace;
}
```

## Typography

- Display: Space Grotesk Variable with a compact, research-editorial hierarchy.
- Body: IBM Plex Sans Variable for prose and controls.
- Mono: IBM Plex Mono for labels and machine-readable identifiers.
- Headings remain roman and use the existing hierarchy.

## Material expression eligibility

- `exhibition`: Project Space receives the high-intensity profile.
- `quiet`: durable modules and stable placeholders with continuing product ownership may receive only the shared quiet substrate.
- `none`: dense configuration and operational surfaces do not receive an individual Material Expression Layer.
- Generic temporary scaffolds, ordinary cards, parameter rows, and invalid elements remain unstyled.

## Point-cloud contract

- The Occluded Point-Cloud Substrate is a deterministic, aria-hidden, pointer-transparent abstract composition anchored to the lower-right of the work area.
- Foreground content and the work-area boundary crop it naturally.
- Particles never encode progress, evidence quality, model structure, or a runtime measurement.
- It is static at rest.
- A module change may produce one 220 ms transform-and-opacity response.
- Reduced motion removes the response entirely.

## Motion stance

- Controls keep their existing purposeful feedback and visible focus treatment.
- Material motion is limited to the point-cloud response triggered by a real module change.
- The system uses named easing and duration tokens only.

## Shared rules

- The persistent module rail, central work area, routes, backend contracts, and module behavior remain unchanged.
- Semantic warning and error colors retain their dedicated meanings.
- Accent color is reserved for active, focused, and current states instead of filling large surfaces.
- New durable surfaces must opt in through the workspace composition seam before receiving material treatment.

## Exports

The Desktop App consumes its GUI-local styling and token sources. Root-level Web/Vite token exports are intentionally retired now that the product UI is Desktop-first.
