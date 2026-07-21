---
status: accepted
---

# Use One Relay Provider for All PaperOrchestra Models

All PaperOrchestra model traffic will use one third-party OpenAI-compatible relay provider, currently selected from the service documented at `https://yunwu.apifox.cn/`. PaperOrchestra owns one provider base URL and one credential source. Provider unification does not require one model: text, search-capable, vision, and image-generation operations may use different model IDs exposed by that same relay. Text, JSON, and vision calls target Vegapunk's `gpt-5.6-sol` where its actual capabilities satisfy the upstream call contract; raster image generation uses a compatible image model from the same provider.

This decision supersedes ADR-0097's separate image-provider credential path. The vendored upstream agents and pipeline will not retain independent Gemini and OpenAI clients; provider adaptation is centralized at their shared model-call boundary while preserving each call's input, output, parsing, retry, and control-flow contract. ADR-0103 fixes Responses as the text, JSON, and vision protocol and the provider's image endpoint as the raster-generation protocol; the mapping from upstream roles to relay model IDs remains a separate decision.

The relay's model catalogue and endpoint compatibility have not yet been verified. Full PaperOrchestra operation therefore depends on later confirmation of text and JSON generation, image understanding, image generation, and a replacement for Gemini Google Search grounding. Missing provider capability must fail explicitly or reopen this decision; it must not silently remove an upstream stage or introduce a second provider.

**Considered Options**

- Use different providers for text, vision, search, and image generation. Rejected to keep PaperOrchestra on one credential, billing, and operational boundary.
- Preserve the upstream Gemini client alongside Vegapunk's OpenAI client. Rejected because it would retain two provider stacks inside the integrated workflow.
