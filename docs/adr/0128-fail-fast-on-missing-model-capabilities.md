# Fail Fast on Missing Model Capabilities

The unified runtime will perform a Capability Preflight before starting Discovery, PaperOrchestra, or evaluation work.
If any enabled role requires a capability that its selected canonical model identity does not provide, the run will fail before making workflow progress; the runtime will not silently switch Provider, model, or protocol.

## Consequences

- Provider switching becomes auditable because one run cannot mix hidden model identities.
- Capability errors must name the affected role, required capability, selected identity, and configuration remedy.
- Optional features must be disabled explicitly before preflight when their capabilities are not available.
