---
status: accepted
---

# Run Each Vendored PaperOrchestra Run in a Child Process

Vegapunk will execute each PaperOrchestra Run in one internal Python child process using the absolute `third_party/paper_orchestra/paper_writing_cli.py` entrypoint. The vendored root and Vegapunk repository root are placed on `PYTHONPATH`, while the child working directory is the run-local Paper workspace. The asynchronous Vegapunk service prepares run-local inputs and configuration, starts and monitors the child, propagates cancellation, captures its logs, and reads its persisted outputs. This keeps PaperOrchestra's synchronous pipeline, root-level imports, module state, and internal thread pools intact while ensuring model-generated plotting code cannot write relative-path artifacts into the vendored source tree.

This is a process boundary inside the same repository and machine, not an external service, container, submodule, or separately deployed application. Provider configuration and credentials still come from Vegapunk's single relay-provider boundary. Process isolation prevents the vendored top-level `methods` and `utils` packages, provider adapter state, and concurrent Figure workers from leaking into other Vegapunk runs.

The synchronous Responses facade inside the child may reuse Vegapunk's existing thread-local pattern: each upstream worker thread owns the event loop and Runtime client needed to perform a blocking helper call without converting upstream agents to async methods. The exact launch manifest, result manifest, and checkpoint protocol remain separate decisions.

**Considered Options**

- Import the vendored agents and pipeline directly into the Vegapunk process. Rejected because upstream assumes repository-root imports and synchronous, thread-based execution; direct embedding would reintroduce broad import, concurrency, and async rewrites.
- Use the vendored source directory itself as the child working directory. Rejected after a real plotting smoke generated relative-path PNG, PDF, and SVG artifacts in the source tree; an absolute CLI path and explicit `PYTHONPATH` preserve imports without making source code the output sandbox.
- Turn PaperOrchestra into a long-running external service. Rejected because file-based single-Paper Runs do not justify another deployed service or network boundary.
