---
status: accepted
---

# Isolate Each Web Launch in a Worker Process

The Web backend supervises one isolated worker process for each admitted Discovery Launch instead of executing Discovery and PaperOrchestra inside the request-serving process. This keeps the Web API responsive, allows process-group Stop and restart reconciliation, and prevents a long model call, experiment failure, or worker exit from taking down the backend; the worker is an execution boundary, not a second user-facing service or a parallel Launch queue.

**Considered Options**

- Run the real pipeline in a backend thread. Rejected because process-level cancellation, descendant cleanup, restart adoption, and protection from `sys.exit` or interpreter-level failures would be unreliable.
- Start a separate user-visible service for Discovery. Rejected because the Web backend already owns the product API and durable Launch lifecycle; only the execution unit needs isolation.
