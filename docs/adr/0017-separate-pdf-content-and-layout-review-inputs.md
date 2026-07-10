---
status: accepted
---

# Separate PDF Content and Layout Review Inputs

PaperOrchestra content review and refinement will use the complete current LaTeX source together with text deterministically extracted from the compiled PDF. Layout review will use page images rendered from that PDF through the existing screenshot utility. The port will remove Gemini's provider-specific `application/pdf` binary input and will not add a native PDF-upload operation to InternAgent's model interface.

LaTeX preserves formulas, citations, structure, and commands, while extracted text verifies the readable compiled content; screenshots carry the visual evidence needed for the default multimodal layout review. PDF text-extraction and page-rendering failures are recorded as failures of their respective stages instead of being conflated or replaced by inferred content.

**Considered Options**

- Extend the model interface with provider-specific PDF upload. Rejected because the same information is already available through portable deterministic text extraction, LaTeX source, and page rendering.
- Use only LaTeX for every review. Rejected because it does not show the actually rendered page layout or confirm the readable compiled text.
- Use only page screenshots for content and layout review. Rejected because screenshots are a lossy and expensive representation of detailed text, equations, and citations.
