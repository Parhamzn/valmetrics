from __future__ import annotations

import functools
import hashlib
import logging
import os
import pickle
import time
from datetime import timedelta
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)


def _resolve_cache_dir() -> Path:
    """Return the configured cache dir, falling back to ~/.dcf_cache/."""
    try:
        from django.conf import settings  # local import so module loads w/o Django

        configured = getattr(settings, "DCF_CACHE_DIR", None)
        if configured:
            return Path(configured)
    except Exception:
        # Django not installed/configured — use default.
        pass
    return Path.home() / ".dcf_cache"


def _make_key(category: str, method_name: str, args: tuple, kwargs: dict) -> str:
    """Produce a deterministic SHA-256 cache key from call metadata."""
    # Sort kwargs so order doesn't change the key. args are already ordered.
    sorted_kwargs = sorted(kwargs.items())
    payload = repr((category, method_name, args, sorted_kwargs))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _cache_path(category: str, key: str) -> Path:
    base = _resolve_cache_dir() / category
    base.mkdir(parents=True, exist_ok=True)
    return base / f"{key}.pkl"


def _read_cache(path: Path, ttl: timedelta) -> tuple[bool, Any]:
    """Return (hit, value). On any read error, return (False, None)."""
    if not path.exists():
        return False, None
    try:
        mtime = path.stat().st_mtime
        if (time.time() - mtime) > ttl.total_seconds():
            return False, None
        with path.open("rb") as f:
            return True, pickle.load(f)
    except Exception as exc:  # corrupt pickle, permission error, etc.
        logger.debug("Cache read failed for %s: %s", path, exc)
        return False, None


def _write_cache(path: Path, value: Any) -> None:
    try:
        # Write to a temp file then rename for atomicity.
        tmp = path.with_suffix(path.suffix + ".tmp")
        with tmp.open("wb") as f:
            pickle.dump(value, f, protocol=pickle.HIGHEST_PROTOCOL)
        os.replace(tmp, path)
    except Exception as exc:
        logger.warning("Cache write failed for %s: %s", path, exc)


def cached(category: str, ttl: timedelta) -> Callable:
    """Decorator: caches the wrapped method's return value to disk.

    Cache key = category + method name + args + kwargs (excluding self).
    Cache dir comes from Django settings.DCF_CACHE_DIR if available, else
    ~/.dcf_cache/. Stored via pickle; reads check file mtime against TTL.
    On any read error (corrupt pickle, etc.) the entry is treated as a
    miss and overwritten.
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(self, *args: Any, **kwargs: Any) -> Any:
            key = _make_key(category, func.__name__, args, kwargs)
            path = _cache_path(category, key)
            hit, value = _read_cache(path, ttl)
            if hit:
                return value
            result = func(self, *args, **kwargs)
            _write_cache(path, result)
            return result

        return wrapper

    return decorator
