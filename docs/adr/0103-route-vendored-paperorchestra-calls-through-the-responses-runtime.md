---
status: accepted
---

# Route Vendored PaperOrchestra Calls Through the Responses Runtime

Text, JSON, and image-understanding calls made by the vendored PaperOrchestra source will retain their upstream helper signatures and return shapes but delegate through a thin compatibility layer to Vegapunk's `ModelRunRequest -> ModelRunResult` Responses Runtime. The upstream agents, prompts, and synchronous pipeline remain structurally intact. Gemini SDK calls and the upstream Chat Completions implementation are removed from the integrated execution path, and the adapter never silently falls back from Responses to Chat Completions.

Raster image generation is the deliberate exception to `ModelRunRequest`: it uses the same relay provider, base configuration, and credential boundary selected by ADR-0102, but calls that provider's OpenAI-compatible image endpoint with a capability-specific image model. Google Search grounding and raw-PDF input require later, explicit input or tool adaptations; this decision does not pretend that either is already supported by Responses.

This supersedes ADR-0016's implementation strategy of injecting `BaseModel` into every PaperOrchestra agent and converting the complete upstream pipeline to native async methods. That strategy unified the runtime but caused broad source and control-flow divergence. Centralizing compatibility at the upstream model-helper boundary preserves the same runtime policy with a much smaller modification surface.

**Considered Options**

- Reuse PaperOrchestra's existing OpenAI Chat Completions branch. Rejected because active Vegapunk OpenAI inference is Responses-native and `gpt-5.6-sol` runtime semantics must not be silently reduced to a Chat-shaped contract.
- Inject `BaseModel` into every upstream agent and make the pipeline asynchronous. Rejected because it repeats the broad rewrite that the source-faithful migration is replacing.
