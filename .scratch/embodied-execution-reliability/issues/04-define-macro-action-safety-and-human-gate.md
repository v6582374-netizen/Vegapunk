# Define macro-action safety and human gate

Type: grilling
Status: resolved
Labels: wayfinder:grilling
Parent: ../map.md
Assignee: Codex
Blocked by: 03-define-g1-deployment-validation-evidence.md
Blocks: 05-define-training-data-and-model-promotion.md

## Question

What is an approved executable macro action, and which deterministic preflight checks, runtime abort conditions, postconditions, human approvals, takeover actions, and durable evidence records govern it?

The decision must preserve the user direction that a hardware macro action may run to completion after preparation, while a deterministic Safety Supervisor retains immediate abort authority. MAS may prepare candidates and analyze feedback but cannot bypass this boundary.

## Resolution

`vegapunk/embodied/safety.py` holds a deterministic `SafetySupervisor`: no learned components, so one observation always yields the same verdict and any abort can be reproduced offline. It owns two powers, preflight admission and instantaneous abort, and nothing outside the module can weaken either.

The design decisions that carry the weight:

- **Advice tightens only.** MAS or a policy may propose narrower limits for one attempt via `with_advice`. Attempting to widen a limit or name an unknown one raises rather than being silently ignored. This is what makes it safe to let a non-deterministic component participate in preparation at all.
- **Missing information is unsafe.** A stale observation aborts instead of assuming the previous state still holds. A precondition the sensors cannot report fails preflight instead of being presumed satisfied.
- **Human stop is judged first.** When a person intervened, the recorded cause is the intervention, not whichever physical limit happened to follow it. Otherwise the trajectory record would misattribute the event.
- **Preflight reports every failure**, not the first, so one round of fixing is enough.
- **The supervisor's safety view carries no images** -- only the quantities an abort decision depends on. A safety decision that needed perception would not be deterministic.

The human gate lives in `admission.py` (approval before the configuration runs) while preflight lives here (whether this moment is safe). Splitting them is deliberate: approval is about a configuration, preflight is about now.
