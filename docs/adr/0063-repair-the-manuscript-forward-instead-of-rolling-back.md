---
status: superseded by ADR-0078
---

# Repair the Manuscript Forward Instead of Rolling Back

A deterministic validation failure does not roll the Living Manuscript back to its previous valid version and does not end the current sculpting invocation. The validators return their exact diagnostics to the same active Manuscript Sculptor, which continues editing the canonical files until they compile and satisfy every deterministic contract. Correct changes already made from the triggering Agent Task Completion remain available during repair instead of being discarded with the invalid portion.

The triggering Agent Task Completion remains inside its Sculptor Completion Barrier while repair continues, and later sculpting triggers wait behind it. A validation failure does not create another Agent Task Completion, spawn a fixer agent, or authorize research; it is ordinary completion work inside the same writing invocation. ADR-0060's outcome criterion still applies, so passing mechanical validation by deleting useful evidence-grounded content is not sufficient. ADR-0072 makes this barrier the normal completion rule rather than a validation-failure exception.

This refines ADR-0050's serialized validation rule and ADR-0062's direct-edit contract. The manuscript may be transiently invalid while the active agent is repairing it, but that state is never treated as the completed input to a later sculpting invocation.

**Considered Options**

- Restore the last valid files after any validation error. Rejected because ordinary LaTeX, citation, and path errors are repairable and rollback would also discard correct updates from the current research outcome.
- Spawn a dedicated repair agent. Rejected because the original sculptor already understands the editorial intent and another handoff would add context loss.
- Accept the invalid files and continue the queue. Rejected because later edits would compound structural errors and obscure which invocation introduced them.
