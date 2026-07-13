---
status: accepted
---

# Use a Responses-Native OpenAI Runtime

All active native OpenAI inference uses `gpt-5.6-sol` through the Responses API behind the project-owned `ModelRunRequest -> ModelRunResult` boundary. OpenAI calls do not expose SDK response shapes to agents and never silently fall back to Chat Completions. Non-OpenAI providers use a separate Chat-compatible adapter with an intentionally smaller capability set rather than forcing every provider through a lowest-common-denominator interface.

The global OpenAI defaults are `reasoning.effort: xhigh`, `max_output_tokens: 128000`, `store: true`, and explicit prompt caching with a `30m` TTL. Role policy remains layered: routine planning and execution use standard mode; stateful tool loops use `reasoning.context: all_turns` where prior reasoning remains relevant; final PaperOrchestra and Deep Research synthesis, refinement, and selected high-value reviews use Pro mode and, for long requests, background execution. This follows OpenAI's [GPT-5.6 guidance](https://developers.openai.com/api/docs/guides/latest-model) while retaining project-specific quality-first defaults.

Agent prompts keep their existing task intent and wording. The Runtime maps system-level text to Responses developer instructions, retains JSON Object mode plus the existing JSON repair fallback, and represents function calls as typed items. Tool continuations preserve the provider-issued `call_id` and use `previous_response_id`; callers may not invent Chat-style tool-call IDs or reconstruct SDK `choices` objects.

Background Responses require `store=true`. A Dossier Run records the provider response ID in `dossier_run.json` immediately after submission and before polling. Reopening the same run retrieves that ID and resumes polling instead of submitting duplicate Pro work; an expired response is replaced only after the provider returns not-found. This implements the polling and recovery semantics in OpenAI's [background mode guide](https://developers.openai.com/api/docs/guides/background) while preserving the stage checkpoint contract from ADR-0019.

The Runtime records the actual model, response ID and status, input/output/reasoning/cache tokens, effective reasoning context, and latency. Hosted tools, Programmatic Tool Calling, and the multi-agent beta are not enabled by this decision; they require separate evaluation and architecture decisions.

**Considered Options**

- Keep native OpenAI on Chat Completions and change only the model string. Rejected because it would omit persisted reasoning, Responses-native state continuation, explicit GPT-5.6 caching, Pro mode, and recoverable background execution.
- Preserve both OpenAI APIs with silent fallback. Rejected because a fallback can discard tool-call state or reasoning semantics while appearing successful.
- Put OpenAI and every compatible gateway behind one neutral Chat-shaped interface. Rejected because it would prevent Responses-only capabilities from becoming first-class and would misrepresent provider support.
- Rewrite Agent prompts during the migration. Rejected because model transport and task instructions are independent changes; prompt changes require their own evidence and evaluation.
- Enable hosted tools, Programmatic Tool Calling, or multi-agent beta immediately. Rejected because the existing application-owned tools and orchestration already define their own execution, evidence, and recovery boundaries.
