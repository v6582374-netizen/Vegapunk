---
status: superseded by ADR-0102
---

# Use a Dedicated Image Generation Provider

The fully restored Plotting Agent uses the separately configured OpenAI-compatible image-generation API at `https://yunwu.ai/v1` for raster method and architecture diagrams. The initial image model is `gemini-3-pro-image-preview`. These non-secret values belong to PaperOrchestra configuration, while the API key is supplied only through `PAPER_ORCHESTRA_IMAGE_API_KEY` and is never committed, copied into the Research Draft, or reused as the primary text-model credential.

Figure planning, Matplotlib code generation, multimodal criticism, captions, and paper writing continue through InternAgent's existing unified Model Runtime. The dedicated provider has the narrow responsibility of turning an accepted image prompt into image bytes; it does not become a second text-writing or research path.

This intentionally creates a narrow exception to ADR-0016's single-provider path because the current InternAgent model contract can inspect images but cannot synthesize them, while full Plotting Agent restoration explicitly requires generated diagrams.

**Considered Options**

- Restore the upstream hard-coded Gemini client and credentials throughout the plotting workflow. Rejected because only raster synthesis requires the additional provider.
- Omit generated diagrams and restore only code-rendered statistical plots. Rejected because that would not restore the full Plotting Agent capability requested for automatic paper generation.
