"""Install temporary ``sys.modules`` entries without evicting real imports.

``unittest.mock.patch.dict(sys.modules, ...)`` restores the whole dictionary on
exit, so every module imported inside the block is dropped again.  For pure
Python that is merely wasteful; for extension modules it is fatal.  NumPy's
``_multiarray_umath`` refuses a second initialisation in one process, so a later
``import numpy`` anywhere in the session fails with ``cannot load module more
than once per process``.

Stubbing is a statement about the named modules only.  This helper restores
exactly those keys and leaves everything else the block imported in place.
"""

from __future__ import annotations

import sys
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from types import ModuleType


@contextmanager
def stub_modules(stubs: Mapping[str, ModuleType]) -> Iterator[None]:
    """Bind ``stubs`` in ``sys.modules`` for the duration of the block."""
    missing = object()
    previous: dict[str, object] = {
        name: sys.modules.get(name, missing) for name in stubs
    }
    sys.modules.update(stubs)
    try:
        yield
    finally:
        for name, original in previous.items():
            if original is missing:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original  # type: ignore[assignment]


__all__ = ["stub_modules"]
