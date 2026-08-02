# End-User Frontend V1 Decision Map

> Historical research record. The planned browser-based End-User Frontend V1 was not retained as the active product surface; implementation focus is now the OpenWorker Desktop App.

Do not use this map as a current product or API specification.

This map records a superseded deployable researcher-facing frontend proposal without changing Vegapunk's research, experiment, queue, model, or GPU logic.
The former Admin Console is retired; its historical references remain only for migration audit context.

## admin-separation: Separate Product And Admin Surfaces

Blocked by: none
Status: resolved
Type: Grilling

### Question

Should the end-user product evolve from the Admin Console or remain a separate frontend?

### Answer

Build a separate researcher-facing frontend.
Do not reuse the Admin Console's navigation or expose its prompts, model catalog, global parameters, or destructive controls.

## v1-audience: Define The Version 1 Audience

Blocked by: none
Status: resolved
Type: Grilling

### Question

Who may use Version 1?

### Answer

Version 1 serves only the project owner's own research use.
It has no authentication, invitation, registration, account-management, or multi-user flows.
Every product request is implicitly made by the Sole Researcher.
The product and its API remain inside the Local Product Boundary and are not accessible over a LAN or public network.

## v1-workflows: Choose The Product Workflows

Blocked by: none
Status: resolved
Type: Grilling

### Question

Which existing Vegapunk workflows belong in Version 1?

### Answer

Version 1 includes both Deep Research Runs and Discovery Launches in one coherent product experience.

## research-submission: Define Discovery Input

Blocked by: v1-workflows
Status: resolved
Type: Grilling

### Question

What may the Sole Researcher provide to a Discovery Launch?

### Answer

The frontend accepts a structured research brief, reference material, data, and optional baseline code through capabilities already supported by the backend.

## backend-boundary: Preserve Existing Backend Logic

Blocked by: v1-workflows, research-submission
Status: resolved
Type: Grilling

### Question

May frontend work alter research or execution behavior?

### Answer

No.
The frontend consumes current behavior and defines integration contracts without changing research, experiment, queue, model, or GPU logic.

## api-contract: Inventory Product-Safe Interfaces

Blocked by: backend-boundary
Status: resolved
Type: Research

### Question

Which existing HTTP, SSE, upload, and artifact contracts can the product frontend consume for both workflows, and which capabilities have no browser-facing contract yet?

### Answer

The inventory is recorded in [End-User Frontend V1 API Contract Inventory](research/end-user-frontend-v1-api-contract.md).
No existing route is safe to expose directly because the Admin Console API exposes global administrative data, raw internals, and destructive controls.
Discovery has reusable internal behavior for submission translation, serial enqueueing, status, graceful stop, resume, structured results, and path-contained artifact reads.
Deep Research has only a synchronous CLI and no HTTP, upload, durable lifecycle, progress, stop, history, or report-resource contract.
The Sci evaluation server is a separate benchmark tool and is not a product API candidate.
A product-owned facade can fill the transport and curation gaps without changing research, experiment, queue, model, or GPU logic.

## researcher-controls: Define Researcher Settings And BYOK

Blocked by: backend-boundary, api-contract
Status: resolved
Type: Research

### Question

Which existing parameters may be exposed as per-work Researcher Run Settings, and how should the Sole Researcher's API keys for administrator-approved Providers and models be stored, selected, and applied without exposing global registries, persisting secrets in research artifacts, or changing model semantics?

### Answer

The decision is recorded in [End-User Frontend V1 Researcher Controls](research/end-user-frontend-v1-researcher-controls.md).
Both workflows expose one administrator-approved Canonical Model Identity and one matching Researcher Model Credential.
Deep Research exposes no algorithmic setting in Version 1 because its current browser candidate is the forced QA path rather than a stable tunable contract.
Discovery additionally exposes `agents.generation.do_survey`, `workflow.loop_rounds`, `workflow.loop_mode`, `workflow.top_ideas_count`, and `experiment.max_runs` under server-supplied limits and an aggregate work budget.
All infrastructure, resource, memory, tool, prompt, agent-tuning, evaluation, coding-backend, and raw catalog fields remain administrator-owned.
Credentials are encrypted at rest, selected by opaque identifier, validated against the chosen Provider, decrypted only inside the trusted worker, and applied to a per-work in-memory catalog and shared Unified Model Runtime.
Secrets never enter task files, configuration snapshots, artifacts, arguments, environment variables, logs, events, or errors.
The immutable non-secret settings and selected model identities are snapshotted for start and resume, while the credential remains a revocable external reference.

## product-api-contract: Define The Researcher-Facing API

Blocked by: api-contract, researcher-controls
Status: resolved
Type: Grilling

### Question

What minimal unauthenticated, sole-researcher HTTP, upload, event, lifecycle, settings, credential-selection, and curated-artifact contract should adapt the existing Deep Research and Discovery implementations without exposing Admin Console resources or changing backend research logic?

### Answer

The contract is recorded in [End-User Frontend V1 Product API Contract](research/end-user-frontend-v1-product-api-contract.md).
Version 1 uses a separate `/api/v1` facade inside the Local Product Boundary, with one implicit Sole Researcher and no authentication or ownership model.
Deep Research Runs and Discovery Launches remain separate resource families with separate histories but share stable lifecycle, progress, activity, error, and artifact shapes.
Creation atomically claims Staged Research Uploads and starts or enqueues immutable work; there are no server-side drafts, separate Start commands, or post-create edits.
Discovery uses the existing Launch Queue and supports explicit Resume only for stopped or reconciled-incomplete Interrupted Launches, while Deep Research and failed work use Run Again to create new identities.
One replayable SSE stream carries durable Research Progress Timeline updates, bounded durable Research Activity Stream output, lifecycle changes, and artifact availability without exposing raw logs or internal reasoning.
Results expose Curated Research Artifacts by opaque identity, including a sanitized Discovery Reproducibility Bundle, and never expose arbitrary paths or the Admin artifact tree.
Sanitized Work Options and credential endpoints replace direct access to the Unified Model Catalog and Run Parameter Registry, while stable error codes replace raw exceptions.

## information-architecture: Structure The Researcher Experience

Blocked by: admin-separation, v1-workflows
Status: resolved
Type: Grilling

### Question

What page hierarchy and navigation let a researcher start, observe, and review both workflows without exposing administrative concepts?

### Answer

Global navigation presents Deep Research and Discovery as sibling product areas because they are parallel architectural entry points.
They do not share a combined work-list destination.
Each product area opens on its own Sole Researcher history list, with active work first, a primary create action, and a create-oriented empty state.
Both detail-page types share a lifecycle shell with identity, status, available actions, Progress, and Results, while their workflow-specific content remains distinct.
Deep Research Results centers the cited report and sources; Discovery Results centers rounds, Candidate Experiments, metrics, Paper outputs, and reproducibility material.
Each product area's create action opens a dedicated page rather than a modal or drawer, so structured input, attachments, validation, and navigation have stable space and URLs.
Active work opens on Progress, while completed work opens on Results; finer view-state behavior is deferred to the prototype.
Progress pairs a persistent Research Progress Timeline, whose ordered core milestones visibly distinguish completed, active, and future work, with a bounded durable Research Activity Stream of curated and redacted terminal-style output.
Allowlisted Researcher Run Settings live in the relevant create page, while Product Settings owns BYOK credentials for administrator-approved Providers and models.

## core-flow-prototype: Validate Both End-To-End Flows

Blocked by: api-contract, product-api-contract, information-architecture
Status: resolved
Type: Prototype

### Question

How should task creation, live progress, interruption, completion, failure, and result review behave for Deep Research Runs and Discovery Launches?

### Answer

The decision is recorded in [End-User Frontend V1 Core Flow Prototype](prototypes/end-user-frontend-v1-core-flow/NOTES.md), with the selected [milestone-focused reference](prototypes/end-user-frontend-v1-core-flow/index.html) as its interactive page.
Creation stays on a dedicated workflow-specific page and atomically creates immutable work, then navigates directly to that work's Progress view without a Draft or separate Start action.
Active work opens on Progress, where the server-supplied Research Progress Timeline remains primary and the bounded curated Research Activity Stream remains visible beside it on desktop and after it on mobile.
Completed work opens on Results, with cited synthesis and sources for Deep Research and selected experiments, quantitative evidence, Paper output, and reproducibility artifacts for Discovery.
All lifecycle controls render from authoritative `allowed_actions`; the frontend never infers them from state, progress, activity, files, or artifacts.
Stopping queued work confirms cancellation and produces Cancelled, while stopping running work confirms Graceful Stop, enters actionless Stopping, and ends as Stopped with completed milestones and retained activity intact.
Discovery Resume preserves the Launch identity, immutable configuration, completed milestones, activity, and prior attempts, then queues a new Execution Attempt at the affected milestone.
Deep Research never resumes, and Run Again always creates a new identity linked to the source work; failed Discovery also uses Run Again.
Failed, Cancelled, Stopped, and Interrupted work opens on Progress with one sanitized explanation and only its authorized recovery actions.
The chronological journey alternative required excessive vertical travel, while the three-pane operations alternative recreated an admin-console posture and compressed the research identity.
The selected reference passed browser checks at 1440 by 900 and 390 by 844 across creation, queueing, running, stop, cancellation, Discovery Resume, interruption, failure, Run Again, and both completed result types, with no document-level horizontal overflow, console errors, or warnings.

## visual-system: Establish The Product Language

Blocked by: information-architecture
Status: resolved
Type: Prototype

### Question

Which typography, color, density, motion, data visualization, and responsive rules make Vegapunk feel like a serious scientific workbench rather than an admin dashboard or marketing page?

### Answer

The decision is recorded in [End-User Frontend V1 Visual System](research/end-user-frontend-v1-visual-system.md), with the selected [Evidence Ledger prototype](prototypes/end-user-frontend-v1-visual-system/index.html) as its reference page.
Use an evidence-led workbench with system sans-serif text, monospace only for identifiers and measurements, cool neutral surfaces, deep-green action and result accents, one-pixel dividers, an 8 px spacing grid, and few shadows or framed cards.
Keep the work identity, lifecycle state, primary finding, quantitative evidence, and curated outputs legible in that order.
Charts require units, baselines, uncertainty where available, direct labels, non-color distinctions, accessible summaries, and underlying values; historical scientific data does not animate.
Repeated navigation and data updates are immediate, while pointer feedback stays within 100 to 180 ms and occasional overlays within 180 to 220 ms, with reduced-motion support.
Desktop uses a 240 px product rail and fluid evidence plus summary columns; mobile replaces the rail with product tabs, uses two-column metric strips, stacks results in reading order, and confines overflow to labeled charts or tables.
The publication-like Research Notebook and dark developer-console Experiment Matrix were rejected as overall systems, though their readable report prose and dense comparison patterns inform individual result views.
The selected reference passed browser checks at 1440 by 900 and 390 by 844 with no document-level horizontal overflow, console errors, or warnings.

## implementation-contract: Define The Build Boundary

Blocked by: api-contract, core-flow-prototype, visual-system
Status: open
Type: Research

### Question

What app structure, shared client types, browser support, accessibility criteria, loading and error states, test coverage, build output, and release checks define a complete frontend Version 1?

### Answer
