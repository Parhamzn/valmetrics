from __future__ import annotations
from .models import WatchlistItem


def is_watched(ticker: str) -> bool:
    if not ticker:
        return False
    try:
        return WatchlistItem.objects.filter(ticker=ticker.upper()).exists()
    except Exception:
        # tolerate "table doesn't exist yet" during initial setup
        return False
