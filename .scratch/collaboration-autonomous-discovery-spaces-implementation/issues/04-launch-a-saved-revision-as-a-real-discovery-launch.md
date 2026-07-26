# 04 - Launch a saved revision as a real Discovery Launch

**What to build:** The Sole Researcher can explicitly start a Discovery Launch from one saved Formatted Discovery Input revision, with the system materializing an immutable start-time record before handing execution to the existing Launch Queue.

**Blocked by:** 03 - Convert sources into editable Formatted Discovery Input.

**Status:** ready-for-agent

- [ ] A Run action is available only after a saved input revision is selected and starts a new Discovery Launch intentionally.
- [ ] The started Launch preserves the selected preparation input and configuration snapshot even if the Preparation changes later.
- [ ] One reusable Preparation can create multiple distinct Discovery Launches without changing Discovery workflow semantics.
