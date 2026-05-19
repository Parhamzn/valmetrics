from __future__ import annotations

import logging
from typing import Optional

from apps.data.base import DataProvider

logger = logging.getLogger(__name__)

_PROVIDER_INSTANCE: Optional[DataProvider] = None


def _resolve_provider_name() -> str:
    """Read settings.DATA_PROVIDER if Django is configured, else default."""
    try:
        from django.conf import settings

        name = getattr(settings, "DATA_PROVIDER", None)
        if name:
            return str(name)
    except Exception:
        pass
    return "yfinance"


def get_provider() -> DataProvider:
    """Return the active data provider (cached at module level)."""
    global _PROVIDER_INSTANCE
    if _PROVIDER_INSTANCE is not None:
        return _PROVIDER_INSTANCE

    name = _resolve_provider_name().lower().strip()
    if name == "yfinance":
        # Imported lazily to keep this module importable even if yfinance
        # isn't installed yet.
        from apps.data.yfinance_provider import YFinanceProvider

        _PROVIDER_INSTANCE = YFinanceProvider()
        return _PROVIDER_INSTANCE

    raise ValueError(f"Unknown DATA_PROVIDER: {name!r}")
