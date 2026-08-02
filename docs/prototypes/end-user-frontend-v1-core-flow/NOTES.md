# End-User Frontend V1 Core Flow Prototype

> Historical prototype. It describes a retired browser product proposal and is not a current implementation target.

Question: How should task creation, live progress, interruption, completion, failure, and result review behave for Deep Research Runs and Discovery Launches?

Three structurally different lifecycle presentations were compared for both workflows.
The selected milestone-focused reference remains on this route.
Its workflow and lifecycle state are URL-addressable through `workflow` and `state` parameters and remain entirely in browser memory.

Run the prototype with one command from the repository root:

```bash
python3 -m http.server 4175 --directory docs/prototypes
```

Open `http://127.0.0.1:4175/end-user-frontend-v1-core-flow/`.

## Verdict

Use one shared lifecycle shell with workflow-specific creation and results.
Creation uses a dedicated page and creates immutable work immediately after validation, then navigates to the new detail page on Progress.
There is no product Draft or separate Start action.

Active work opens on Progress.
Progress leads with the server-supplied Research Progress Timeline and keeps the bounded, curated Research Activity Stream beside it on desktop and after it on mobile.
The interface never derives progress or actions from logs, filenames, or state names.
It renders `allowed_actions` from the product API.

Stopping queued work asks for confirmation and ends as Cancelled without execution.
Stopping running work asks for confirmation, enters Stopping with no further action, and ends as Stopped after Graceful Stop completes.
Completed milestones and retained activity remain visible through stopping, failure, and interruption.

Discovery Resume keeps the Launch identity, progress, activity, completed milestones, and prior attempts, then adds a queued Execution Attempt at the affected milestone.
Deep Research never offers Resume.
Run Again creates a new identity for either workflow, links it to the source work, and reuses the immutable retained submission.
Failed Discovery work also uses Run Again rather than Resume.

Completed work opens on Results.
Deep Research Results leads with the cited synthesis, evidence base, sources, and report artifacts.
Discovery Results leads with the selected result, quantitative evidence with units and uncertainty, Paper output, and reproducibility artifacts.
Failed, Stopped, Cancelled, and Interrupted work opens on Progress with one sanitized explanation and only the recovery actions authorized by the API.

The chronological Research Journey variant was rejected because stable progress and live activity required excessive vertical travel.
The three-pane Operations Split variant was rejected because it recreated an admin-console posture and compressed the research identity.
The selected milestone-focused layout kept work identity, available action, durable progress, live activity, and result evidence legible in that order.

The reference passed browser checks at 1440 by 900 and 390 by 844 for creation, queueing, running, Graceful Stop, cancellation, Discovery Resume, interruption, failure, Run Again, and both completed result types.
The final reference had no document-level horizontal overflow, console errors, or warnings.
