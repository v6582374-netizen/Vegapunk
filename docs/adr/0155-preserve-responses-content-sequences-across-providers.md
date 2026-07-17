Status: accepted

# Preserve Responses Content Sequences Across Providers

The Unified Model Runtime preserves every ordered Responses Content Sequence without flattening consecutive text items or repackaging text, image, or file items to accommodate a Provider.
Both the official [OpenAI Responses documentation](https://developers.openai.com/api/docs/guides/images-vision) and [Alibaba Cloud Model Studio's Qwen Responses reference](https://help.aliyun.com/zh/model-studio/qwen-api-via-openai-responses) define typed content arrays, so their item boundaries are part of the supported request contract.
A Provider that cannot process a required sequence is not made compatible by mutating the request shape; its fixed Catalog eligibility determines whether it is available instead.

## Consequences

- Image and file items remain subject to the selected model's declared capability.
- Multipart-sequence support is determined by the human-maintained Catalog during development; the Runtime performs no dedicated probe or compatibility negotiation.
