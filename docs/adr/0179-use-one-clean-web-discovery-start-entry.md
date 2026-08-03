---
status: accepted
---

# Use One Clean Web Discovery Start Entry

Preparation is the only user input phase: once it has produced a saved, launch-ready Discovery Execution Input, Web invokes one simple backend Start Entry with the selected revision and asks for nothing else. That entry starts the existing automatic Discovery launcher; it does not expose task construction, extra uploads, stage controls, or a second Web-specific orchestration path.

This supersedes the overly specific framing in ADR-0178. Any filesystem or argument adaptation required to call the existing launcher is an internal detail of the Start Entry, not an additional product step or a new user-facing concept.
