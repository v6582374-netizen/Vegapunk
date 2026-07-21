# PRD: Catalog-Driven Unified Model Runtime

## Problem Statement

Vegapunk currently has several overlapping model-resolution paths across discovery, Deep Research, Sci evaluator, memory, and PaperOrchestra.

Provider names, model names, protocol choices, credentials, retry behavior, concurrency limits, and capability assumptions are distributed across configuration files, factories, adapters, and caller-local branches.

Some callers still infer a Provider from a model name or translate legacy Gemini names into another model, which makes the configured model identity different from the model that is actually requested.

PaperOrchestra and Deep Research also maintain provider-specific bridges instead of consuming one project-wide model contract.

The existing Responses background execution path is not supported by Qwen and introduces asynchronous submission, polling, checkpoint, and recovery branches that are not required by this project.

As a result, changing the Provider or model requires coordinated edits, and a low-cost full-system smoke run cannot exercise the same architecture that production runs use.

## Solution

Introduce one catalog-driven Unified Model Runtime for every active in-process model call.

The Runtime resolves explicit `provider/model` identities from one model catalog, validates fixed capabilities at process startup, selects the declared protocol, owns Provider clients, and exposes typed operations for text, JSON, tools, vision, image generation, and embeddings.

The active generative Provider set is limited to `relay` and `qwen`.

The default run uses `qwen/qwen3.7-max` as the Active Text Model, `qwen/qwen3.6-plus` for vision, `qwen/qwen-image-2.0-pro` for image generation, and `local/BAAI-bge-base-en-v1.5` for embeddings.

Relay remains available as the alternate text and image Provider through the same catalog and Runtime contract.

All model requests are synchronous from the Runtime contract's perspective.

Provider-side Responses `background` execution is disabled globally, while prompt background text and Deep Research background research remain unrelated features.

Provider selection, protocol fallback, model fallback, and runtime capability negotiation are deliberately excluded.

## User Stories

1. As a project maintainer, I want one catalog to define every in-process Provider and model, so that changing the model does not require editing multiple consumers.

2. As a project maintainer, I want to switch the Active Text Model by changing one canonical binding, so that all text-producing and text-evaluating roles follow the same model.

3. As a project maintainer, I want to switch between Relay and Qwen without changing agent code, so that Provider experiments remain configuration work.

4. As a project maintainer, I want each model identity to include its Provider explicitly, so that `qwen/qwen3.7-max` can never be silently routed to Relay.

5. As a project maintainer, I want legacy aliases such as Gemini-to-GPT mappings rejected, so that configuration names and actual requests remain auditable.

6. As a project maintainer, I want startup validation to reject a model that lacks a required capability, so that an unsupported vision, tool, JSON, or reasoning request fails before a long run starts.

7. As a project maintainer, I want capability eligibility fixed during development, so that production requests do not perform unpredictable model negotiation.

8. As a Discovery user, I want generation, reflection, evolution, refinement, ranking, survey, and candidate selection to use one Active Text Model, so that a run has a consistent reasoning identity.

9. As a Deep Research user, I want planning, execution, coordination, synthesis, and query analysis to use the same Runtime, so that Deep Research does not silently bypass project Provider policy.

10. As a PaperOrchestra user, I want writing, review, plotting, and caption calls to use the injected Runtime, so that PaperOrchestra does not create its own SDK clients or Provider factory.

11. As a Sci evaluator user, I want textual, JSON, reasoning, and image-review calls to use the Runtime, so that evaluation follows the same model and retry policy as discovery.

12. As a memory subsystem user, I want embedding requests to use an explicit embedding binding, so that retrieval infrastructure is not accidentally coupled to the text model.

13. As a maintainer, I want the Long Memory index treated as disposable, so that changing the embedding model can rebuild the index without preserving an incompatible vector space.

14. As a model adapter author, I want typed Runtime requests instead of SDK response objects at call sites, so that Provider-specific response shapes remain behind one boundary.

15. As a model adapter author, I want Relay GPT models to use their declared Responses protocol, so that reasoning, structured output, tools, and context continuation retain their intended semantics.

16. As a model adapter author, I want Qwen text and vision models to use their declared Responses protocol, so that Qwen-specific request omissions do not require caller branches.

17. As a PaperOrchestra plotting user, I want `qwen-image-2.0-pro` to use the native DashScope image endpoint, so that image generation works even though the image API is not an OpenAI-compatible text endpoint.

18. As a maintainer, I want one model per request, so that a single request cannot silently combine incompatible models or Providers.

19. As a maintainer, I want all model operations to have centralized concurrency limits, so that account capacity is controlled independently of workflow-level parallelism.

20. As a maintainer, I want text, JSON, vision, tools, image generation, and embedding operations to share bounded retries, so that transient Provider failures do not terminate a long run unnecessarily.

21. As a maintainer, I want retries bounded by both attempts and elapsed time, so that a request cannot retry forever or consume the entire process indefinitely.

22. As a maintainer, I want retries to keep the same Provider, model, and protocol, so that retry behavior cannot change the meaning of a run.

23. As a maintainer, I want protocol errors to fail explicitly, so that the Runtime never silently changes from Responses to Chat Completions.

24. As a maintainer, I want Provider-side background execution disabled for every model operation, so that Relay and Qwen share one synchronous execution semantic.

25. As a maintainer, I want ordinary `previous_response_id` continuation to remain available independently of background execution, so that tool loops and Responses context state are not lost.

26. As a maintainer, I want an interrupted process to use the catalog selected at its next process start, so that one process never changes Provider or model policy while running.

27. As a maintainer, I want missing credentials and invalid endpoint configuration reported at startup, so that failures happen before a costly E2E run.

28. As a developer, I want a low-cost Runtime smoke test with Qwen, so that the complete call surface can be exercised without paying for a full discovery loop.

29. As a developer, I want a Relay smoke test through the same Runtime contract, so that switching back to the existing Provider remains a supported regression path.

30. As a maintainer, I want unused vendored Provider implementations excluded from active dispatch, so that historical code cannot reintroduce hidden Provider behavior.

31. As a maintainer, I want the Experiment Backend selection to remain separate from Model Provider selection, so that Claude Code, Qwen Code, and iFlow workflows do not alter in-process LLM routing.

32. As a maintainer, I want existing prompts, research artifacts, experiment execution, and scientific selection semantics preserved, so that this migration changes model infrastructure without changing the research workflow.

## Implementation Decisions

- The canonical configuration source is `config/model_catalog.yaml`.

- A Canonical Model Identity is represented as `provider/model`, for example `relay/gpt-5.6-sol` or `qwen/qwen3.7-max`.

- The catalog owns Provider endpoint, credential reference, headers, transport settings, timeout policy, declared protocol, retry policy, concurrency policy, and capability declarations.

- The catalog exposes one `active_text_model` binding and a `capability_models` map containing fixed bindings for `vision`, `image_generation`, and `embedding`.

- The Active Text Model is `qwen/qwen3.7-max` for the initial Qwen-oriented configuration.

- The vision binding is `qwen/qwen3.6-plus`.

- The image-generation binding is `qwen/qwen-image-2.0-pro`.

- The embedding binding is `local/BAAI-bge-base-en-v1.5` and may use a different Provider from generative models.

- The active generative Provider set is `relay` and `qwen`.

- The Qwen Provider authenticates with a standard DashScope API key and supports the OpenAI-compatible DashScope Responses endpoint for text and vision.

- Qwen image generation uses the native DashScope multimodal image-generation endpoint and its synchronous result contract, not the OpenAI-compatible text endpoint.

- Relay GPT models use the declared Responses protocol.

- Every model identity declares exactly one protocol.

- The Runtime does not implement Provider fallback, model fallback, or protocol fallback.

- The Runtime does not infer a Provider from a model-name prefix.

- The Runtime does not preserve compatibility aliases or translate Gemini names into GPT names.

- The Runtime exposes typed capability operations for text, structured JSON, tool calls, vision input, image generation, and embeddings.

- All active consumers receive one explicit Runtime instance per process.

- Consumers do not create SDK clients, parse Provider configuration, choose protocols, or own model request semaphores and retry loops.

- Each request resolves to exactly one Canonical Model Identity that covers every capability required by that request.

- Capability eligibility is checked during Runtime construction or preflight and is not negotiated per request.

- Provider-side Responses `background` execution is removed from the active model contract and is never sent.

- Background-specific submission, polling, cancellation, and response checkpoint branches are removed from the active Runtime path.

- Ordinary Responses continuation through `previous_response_id` remains supported where the declared protocol supports it.

- Prompt background fields, Deep Research background research, workflow background threads, and scientific background text remain separate concepts and are not removed.

- Request timeout remains a generic Runtime policy and is not named or configured as a background timeout.

- All model operations use centralized bounded retries with an initial budget of 8 attempts, a maximum elapsed budget of 900 seconds, an initial backoff of 2 seconds, and a maximum backoff of 60 seconds.

- Retries retain the same Provider, model, and protocol.

- Text, JSON, vision, tools, image generation, and embedding operations are all eligible for the shared retry policy.

- Provider request concurrency is enforced by the Runtime and is independent of workflow parallelism.

- Project-owned legacy adapters, DR model selectors, old Provider configuration, and caller-local Provider branches are deleted after migration.

- Unused vendored CAMEL or third-party implementations may remain in the repository but cannot enter active dispatch.

- Legacy configuration is rejected rather than silently translated after migration.

- A changed embedding model invalidates the disposable Long Memory index, which may be deleted and rebuilt from the underlying records.

- The Experiment Backend remains outside this Runtime and is not changed by this PRD.

## Testing Decisions

- The highest testing seam is the Unified Model Runtime contract.

- Contract tests use fake Provider adapters to verify typed request mapping, capability validation, response normalization, continuation, retries, concurrency, timeout behavior, and error classification without depending on network availability.

- Catalog preflight tests verify canonical identities, declared protocols, capability declarations, Provider membership, credential references, and invalid legacy configuration rejection.

- Relay and Qwen adapter tests verify that each declared protocol receives the correct request shape and that unsupported fields are omitted rather than negotiated away.

- Tool-loop tests verify that function-call IDs and `previous_response_id` continuation survive through the Runtime contract.

- Image-generation tests verify native image endpoint mapping, returned image bytes or URLs, aspect-ratio mapping, and bounded retries.

- Embedding tests verify explicit Provider/model selection and disposable-index rebuild behavior.

- Concurrency tests verify that Runtime admission limits model requests without changing workflow-level worker counts.

- Retry tests verify attempt and elapsed-time budgets, exponential backoff caps, and the invariant that retries do not change Provider, model, or protocol.

- Deep Research, PaperOrchestra, and Sci evaluator tests verify injected Runtime usage at their existing integration seams.

- A low-cost external smoke suite may probe Qwen text, vision, image generation, and embedding capabilities with real credentials, but it is not required for ordinary offline unit tests.

- A Relay smoke suite uses the same Runtime entry point to confirm that the alternate Provider remains selectable.

- Tests assert externally observable behavior and Runtime contracts rather than private adapter helper structure.

- Existing model-runtime, tool-loop, PaperOrchestra bridge, DR, and Sci evaluator tests are extended or replaced at the Runtime seam instead of preserving tests for deleted Provider-specific branches.

## Out of Scope

- Experiment CLI Backends such as Claude Code, Qwen Code, and iFlow.

- Runtime Provider failover or model failover.

- Protocol fallback from Responses to Chat Completions.

- Runtime capability negotiation or automatic model selection.

- Provider-side background execution, polling, or remote in-flight recovery.

- Changes to research prompts, Discovery state transitions, experiment code execution, scientific metrics, or paper scientific content.

- Preservation or migration of existing Long Memory vector indexes.

- Adding Providers beyond Relay and Qwen, except for the separately declared local embedding implementation.

- Rewriting or removing unrelated vendored third-party code that is not reachable from active dispatch.

- Solving external network outages, Provider concurrency incidents, or account-level service instability beyond the Runtime's bounded retry and concurrency policies.

## Further Notes

Development probes have already confirmed synchronous Qwen Responses behavior for the text model and successful vision input for the selected Qwen vision model.

The selected Qwen image model has also returned a valid PNG through the native DashScope multimodal generation endpoint.

Qwen Responses rejects `background=true`, which is the direct reason the project uses one synchronous execution semantic for all Providers.

The migration should be performed in this order: catalog and typed Runtime contract, Provider adapters, Runtime injection, caller migration, deletion of legacy dispatch, then contract and E2E smoke validation.

The implementation must preserve the distinction between Model Provider, Experiment Backend, Background Model Execution, prompt background context, and Deep Research background research.
