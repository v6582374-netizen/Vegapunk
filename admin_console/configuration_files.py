"""Process-local transaction boundary for source configuration files."""

from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager

_SOURCE_CONFIGURATION_LOCK = threading.RLock()


@contextmanager
def source_configuration_transaction() -> Iterator[None]:
    with _SOURCE_CONFIGURATION_LOCK:
        yield
