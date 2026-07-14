"""Expose the ResearchClawBench evaluator through InternAgent's namespace.

The evaluator is maintained by the ``sci_tasks`` submodule.  A regular Python
package bridge is used here instead of a filesystem symlink so Windows Git
checkouts preserve a valid importable package.
"""

from pathlib import Path


_EVALUATION_PACKAGE = (
    Path(__file__).resolve().parents[2] / "sci_tasks" / "evaluation"
)

# Let Python resolve ``internagent.rcb_evaluation.<module>`` from the evaluator
# package owned by the initialized sci_tasks submodule.
__path__ = [str(_EVALUATION_PACKAGE)]
