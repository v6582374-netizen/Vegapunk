---
status: accepted
---

# Use a Responses-Native OpenAI Runtime

All active native OpenAI inference uses `gpt-5.6-sol` through the Responses API behind the project-owned `ModelRunRequest -> ModelRunResult` boundary. OpenAI calls do not expose SDK response shapes to agents and never silently fall back to Chat Completions. Non-OpenAI providers use a separate Chat-compatible adapter with an intentionally smaller capability set rather than forcing every provider through a lowest-common-denominator interface.

The historical migration defaults were `reasoning.effort: xhigh`, `max_output_tokens: 128000`, and `store: true`, with a `30m` prompt-cache TTL. ADR-0107 supersedes only the output-token default: current Responses requests leave `max_output_tokens` unset unless a caller explicitly supplies a ceiling. The Runtime supports both official explicit and implicit caching. The built-in `ai.cloudyz.top` deployment uses implicit mode because that gateway rejects GPT-5.6 content-level cache breakpoints; this is an explicit configuration choice, not a runtime fallback. Role policy remains layered: routine planning and execution use standard mode; stateful tool loops use `reasoning.context: all_turns` where prior reasoning remains relevant; selected Deep Research synthesis and review work may use Pro/background according to its own role policy. The source-faithful PaperOrchestra bridge preserves upstream calls as synchronous standard requests rather than adding per-stage Pro/background behavior. This follows OpenAI's [GPT-5.6 guidance](https://developers.openai.com/api/docs/guides/latest-model) while retaining project-specific quality-first defaults.

Agent prompts keep their existing task intent and wording. The Runtime maps system-level text to Responses developer instructions, retains JSON Object mode plus the existing JSON repair fallback, and represents function calls as typed items. Tool continuations preserve the provider-issued `call_id`. Server-state deployments use `previous_response_id`; the built-in gateway explicitly uses stateless replay because it does not implement response retrieval, so the Runtime resends prior input and every output item before the matching function result. Callers may not invent Chat-style tool-call IDs or reconstruct SDK `choices` objects.

Background Responses require `store=true`. Runtime consumers that opt into background execution must persist and recover provider response IDs according to their own workflow contracts. Under ADR-0105, the source-faithful PaperOrchestra baseline deliberately does not use a `paper_orchestra_run.json` manifest, durable stage checkpoints, or host-restart recovery; its child process performs ordinary synchronous requests and reports failure if it is interrupted. The built-in gateway currently completes background requests synchronously and has no retrieve endpoint, so other consumers cannot recover an in-flight remote request after process interruption when using that deployment.

The Runtime records the actual model, response ID and status, input/output/reasoning/cache tokens, effective reasoning context, and latency. Hosted tools, Programmatic Tool Calling, and the multi-agent beta are not enabled by this decision; they require separate evaluation and architecture decisions.

**Considered Options**

- Keep native OpenAI on Chat Completions and change only the model string. Rejected because it would omit persisted reasoning, Responses-native state continuation, explicit GPT-5.6 caching, Pro mode, and recoverable background execution.
- Preserve both OpenAI APIs with silent fallback. Rejected because a fallback can discard tool-call state or reasoning semantics while appearing successful.
- Put OpenAI and every compatible gateway behind one neutral Chat-shaped interface. Rejected because it would prevent Responses-only capabilities from becoming first-class and would misrepresent provider support.
- Rewrite Agent prompts during the migration. Rejected because model transport and task instructions are independent changes; prompt changes require their own evidence and evaluation.
- Enable hosted tools, Programmatic Tool Calling, or multi-agent beta immediately. Rejected because the existing application-owned tools and orchestration already define their own execution, evidence, and recovery boundaries.
