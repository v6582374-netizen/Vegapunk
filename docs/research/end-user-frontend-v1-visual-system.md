# End-User Frontend V1 Visual System

## Decision

Use an evidence-led workbench built on the prototype's Evidence Ledger variant.
The product shell should make the work identity, lifecycle state, primary finding, quantitative evidence, and curated outputs legible in that order.
It should feel lighter and more readable than the Admin Console while remaining denser and more operational than a publication or marketing page.

The selected reference page is [the visual system prototype](../prototypes/end-user-frontend-v1-visual-system/index.html).

## Prototype Evidence

The prototype compared three structurally different presentations of the same completed Discovery Launch at 1440 by 900 and 390 by 844 viewports.
The Evidence Ledger balanced scanning and reading across both viewports without document-level horizontal overflow.
The Research Notebook made the narrative easy to read but presented the product as a publication and delayed access to operational evidence.
The Experiment Matrix made comparison fast but reproduced the density, dark chrome, and inspector posture of a developer console.

## Typography

Use the operating system sans-serif stack for navigation, controls, metadata, findings, and report content.
Use the operating system monospace stack only for identifiers, timestamps, parameter values, measurements, and tabular numbers.
Use 28 px desktop and 23 to 24 px mobile type for detail-page titles, 16 to 18 px for section headings, 14 px for reading text, and 12 to 13 px for dense metadata and tables.
Use weight, whitespace, and dividers for hierarchy rather than oversized display type.
Keep letter spacing at zero and use tabular numerals for comparable measurements.

## Color And Materials

Use neutral white and cool gray-green surfaces with dark neutral text, one-pixel dividers, and minimal shadow.
Use deep green for primary actions, successful lifecycle states, selected evidence, and positive results.
Reserve blue for keyboard focus, amber for warnings or paused work, and red for failures or destructive actions.
Every status and chart series must remain identifiable through text, shape, line treatment, or position without relying on color alone.
Do not use gradients, tinted page backgrounds that dominate the product, translucent decoration, or a persistent dark workbench theme.

Reference tokens from the prototype are `#ffffff` for the primary surface, `#f7f9f8` for the page surface, `#dce2df` for dividers, `#1e2622` for primary text, `#176b46` for the primary action, and `#2d66d4` for focus.

## Density And Layout

Use an 8 px spacing grid, a 56 to 60 px top toolbar, a 240 px desktop product rail, 40 to 44 px data rows, and radii no larger than 6 px for product surfaces.
Prefer full-width sections, metric strips, tables, and border-separated panes over collections of floating cards.
Keep the lifecycle shell shared between workflows, but let the evidence and result content determine the detail-page body.
On wide screens, place primary evidence in a fluid column and a roughly 300 px finding and output summary beside it.
Allow local scrolling inside wide charts and tables instead of widening the document.

## Data Visualization

Lead with the scientific question or outcome, not the chart type.
Label axes with units, show baselines and uncertainty when available, and directly label decisive values instead of requiring a detached legend.
Pair charts with an accessible summary and a table or list that exposes the underlying values.
Use a single accent series for the selected result and neutral treatments for comparison series.
Do not animate historical measurements or use decorative chart motion.

## Motion

Repeated navigation, tab changes, terminal updates, table updates, and keyboard-initiated actions should be immediate.
Use 100 to 160 ms transform feedback for presses and 120 to 180 ms color transitions for pointer hover.
Use 180 to 220 ms ease-out transitions only for occasional overlays, drawers, and messages whose entrance needs spatial explanation.
Animate only transform and opacity, keep transitions interruptible, and remove positional motion under `prefers-reduced-motion`.

## Responsive Behavior

Below 760 px, replace the desktop rail with compact product-area tabs, keep the work identity and available action first, and render metrics as a two-column strip.
Stack evidence, candidates, findings, quality notes, and outputs in that order unless the workflow state requires the finding to lead.
Keep page titles at a stable mobile size and let them wrap naturally.
Charts and tables may scroll within their own labeled region, but the page itself must not scroll horizontally.
The prototype switcher is not part of the product and must never ship.

## Accessibility Baseline

Use semantic landmarks, a single page heading, ordered heading levels, table headers, chart names and descriptions, and visible three-pixel keyboard focus.
Target WCAG 2.2 AA contrast, 44 px touch targets for primary mobile controls, and text labels for lifecycle and validation states.
Preserve a logical reading order when desktop panes collapse, and never hide result information behind hover alone.

## Deferred Decisions

This decision does not select a frontend framework, component library, charting library, token implementation, or report-rendering package.
Those choices belong to `implementation-contract` and should reproduce these rules with the fewest project dependencies.
