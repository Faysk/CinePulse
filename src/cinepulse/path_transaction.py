from __future__ import annotations

import os
import threading
from functools import wraps
from pathlib import Path
from typing import Callable, ParamSpec, TypeVar


_P = ParamSpec("_P")
_R = TypeVar("_R")
_LOCKS_GUARD = threading.Lock()
_LOCKS: dict[str, threading.RLock] = {}


def path_mutation_lock(path: Path) -> threading.RLock:
    """Return the process-wide mutation lock for one durable JSON path."""
    key = os.path.normcase(str(Path(path).resolve(strict=False)))
    with _LOCKS_GUARD:
        return _LOCKS.setdefault(key, threading.RLock())


def serialized_path_mutation(method: Callable[_P, _R]) -> Callable[_P, _R]:
    """Serialize a store read-modify-write transaction using its path attribute."""
    @wraps(method)
    def guarded(*args: _P.args, **kwargs: _P.kwargs) -> _R:
        if not args:
            return method(*args, **kwargs)
        owner = args[0]
        path = Path(getattr(owner, "path"))
        with path_mutation_lock(path):
            return method(*args, **kwargs)
    return guarded
