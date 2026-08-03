---
status: accepted
---

# Start Web Discovery from a Saved Revision Reference

The Web Discovery Start Entry accepts only the identity of the saved Preparation revision that is being launched; the backend reads the complete structured input and source snapshot from its own durable state. The request also requires an idempotency key so retries from a browser or network reconnect replay the original Launch rather than creating a duplicate. Raw files and structured input are never resubmitted at Run time.

This keeps the start operation a small command over an already validated input, prevents client and server copies from diverging, avoids resending large files, and makes duplicate-click behavior explicit.
