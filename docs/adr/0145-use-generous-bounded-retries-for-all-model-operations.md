Status: accepted

# Use Generous Bounded Retries for All Model Operations

Because the active Provider is intermittently unreliable and preserving a long-running process is more important than avoiding duplicate model work, the Unified Model Runtime may retry text, JSON, vision, tool, image, and embedding operations.
Retries remain bounded by per-request attempt and time budgets, use backoff, and keep the same Provider, Canonical Model Identity, and declared protocol; the runtime does not retry forever or switch routing identities.

## Consequences

- Image-generation retries are explicitly allowed even when they may repeat cost or produce a duplicate image.
- Tool-call retries are also allowed, so callers and tool implementations must tolerate duplicate execution where possible.
- A persistent Provider outage eventually becomes a clear terminal error rather than an endless process hang.
