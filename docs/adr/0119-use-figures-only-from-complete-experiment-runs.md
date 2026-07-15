---
status: superseded by ADR-0122
---

# Use Figures Only from Complete Experiment Runs

An existing Experiment-Sourced Figure is eligible for the Paper Input Bundle only when it belongs to a Complete Experiment Run and is explicitly referenced by that Run's valid Run Report under ADR-0117. A Complete Experiment Run has valid outcome artifacts and a valid `report/report.md`; figure files from failed or incomplete Runs are excluded even when a partial report or filesystem scan can locate them.

Failure and incompleteness remain part of the Experimental Record under ADR-0111 and ADR-0113: their text, metrics, logs, tracebacks, and limitations are not hidden. They simply cannot automatically supply visual evidence. A scientifically valid negative result that should contribute a figure must itself be preserved as a Complete Experiment Run with valid outcomes and a Run Report rather than relying on a failed execution state.
