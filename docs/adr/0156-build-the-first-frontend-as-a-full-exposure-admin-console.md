Status: superseded by the Desktop-first product direction

> Historical ADR. This decision describes the retired root Web/Admin Console and is retained for architectural audit history. The active product UI is now the OpenWorker Desktop App; the Python API capabilities below remain reusable backend services.

# Build the First Frontend as a Full-Exposure Admin Console

The first Vegapunk frontend is the Admin Console: a developer-facing Desktop Web Console whose purpose is fast test-and-modify iteration on the research pipeline, not end-user research work.
It exposes the complete internal surface — every prompt in the system joins the Prompt Library, including infrastructure and scaffolding prompts and prompts embedded in vendored code, and every run parameter joins the Run Parameter Registry as a described, validated structured form.
A curated user-facing console is a separate later deliverable and does not constrain what the Admin Console shows.
The console has no accounts, runs Launches through a service-wide serial Launch Queue, and follows the running Launch through the Live Launch View with a Graceful Stop control.

**Considered Options**

- Expose only a curated subset of scientific-behavior prompts and high-value parameters. Rejected because the console's purpose is developer testing, where infrastructure prompts and obscure parameters are exactly the things under investigation.
- Build the end-user product first. Rejected because its curation decisions depend on testing experience that only a full-exposure console can provide.

## Consequences

- Every embedded prompt must be externalized from code, including those inside vendored frameworks; this is a large mechanical migration and editing infrastructure prompts can break parsing contracts, which is accepted for a developer-only tool.
- Each parameter must carry a maintained description, type, and validation rule for its structured form; nested structures such as the model catalog need dedicated form design.
- Nothing in the console may assume an untrusted user; safety rails are limited to validation, not permission.
