---
status: accepted
---

# Use the InternAgent Model Interface for PaperOrchestra

Every ported PaperOrchestra agent will receive the same `internagent.mas.models.BaseModel` instance created by InternAgent's `ModelFactory`. Text and LaTeX generation use `generate`, structured outputs use `generate_json`, and image-bearing reviews use `generate_with_messages`. The ported pipeline and agents become natively asynchronous and directly await these methods; no synchronous bridge or PaperOrchestra-specific model gateway is introduced.

PaperOrchestra's legacy Gemini and OpenAI text helpers, provider clients, hard-coded text-model names, API-key loading, and text-provider selection are removed from the ported runtime. A configured primary model that cannot process the default multimodal layout review produces an explicit stage failure recorded in the PaperOrchestra Run instead of silently switching providers or skipping the review. ADR-0097 separately permits an image-only provider for raster method and architecture diagrams.

**Considered Options**

- Preserve PaperOrchestra's provider clients behind its existing helper functions. Rejected because it would create a second model configuration and credential path inside InternAgent.
- Add a new PaperOrchestra model-adapter abstraction over `BaseModel`. Rejected because the existing InternAgent interface already provides the required text, JSON, and message operations.
- Wrap async InternAgent calls with synchronous entrypoints inside each agent. Rejected because the surrounding InternAgent workflow is already asynchronous and nested event-loop bridges add failure modes without a compatibility benefit.
