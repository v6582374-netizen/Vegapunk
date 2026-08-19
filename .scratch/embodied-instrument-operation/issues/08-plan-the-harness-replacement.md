# Plan the harness replacement

Type: grilling
Status: resolved
Assignee: codex
Labels: wayfinder:grilling
Blocked by: 04, 07

## Question

What is the smallest safe migration from the current embodied package to the
independent Embodied Operation Harness?

Name the replacement modules and their public seams, the retained governance
modules, the deletion boundary, and the tests or artifacts that make the
cutover reversible. The answer is an implementation handoff plan, not code.

## Answer

**Additive, not a migration. `vegapunk/operation/` was built alongside
`vegapunk/embodied/` and nothing was deleted.**

That is the smallest safe cutover available here, and the reason is arithmetic
rather than caution: the discovery-derived package is ~12,000 lines with ~11,000
lines of tests behind it, and it is wired into a shipped desktop surface
(`coworker/server/embodied.py`, its worker, and the GUI's workbench). Deleting it
to make room for a package that has never held a robot would trade a working
simulated bench for an unproven one.

### What exists now

    vegapunk/operation/     11 modules, ~3,400 lines
    tests/operation/        13 files, 204 tests, all green
    scripts/run_operation.py        convert | train | dryrun | readiness
    scripts/patch_twist2_deadman.py the one edit outside this repo

### The deletion boundary, deferred on purpose

Nothing in `operation` imports `embodied`, and nothing in `embodied` imports
`operation`. So the deletion is a *later* decision with a clear trigger: once the
new harness has driven one supervised hardware run, the discovery-derived
assembly (`intake`, `adaptation`, `objective`, `search`, `harness`) and the
direct-joint actuation seam (`runtime`, `loop`, `skill`, `RobotInterface`) can be
removed in one commit. Until then they cost nothing but disk, and they still run
the desktop surface.

### What makes the cutover reversible

- The two packages share no module, no state, and no ledger directory.
- `pytest tests/operation` and `pytest tests/embodied` pass independently.
- The only change outside this repository is the vendored tracker patch, which
  writes a `.orig` backup and supports `--revert`.
- `pytest.ini` gained two ROS plugin exclusions; nothing else in the repo was
  modified.

### Handoff

`scripts/run_operation.py readiness` is the handoff document. It prints what is
built, what the harness itself reports as missing, and the six physical acts that
need a human -- generated from the current state rather than written down once and
left to rot.
