"""Smoke test the Earnings Power Value flow against real tickers.

Bootstraps Django, derives defaults for a handful of representative companies,
runs the engine, and prints a compact comparison line per ticker. Designed to
be invoked directly::

    .venv/bin/python apps/valuation/tests_epv_pages.py
"""

from __future__ import annotations

import os
import sys
import traceback

# --- Make repo importable, then bootstrap Django ---------------------------
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.abspath(os.path.join(_THIS_DIR, os.pardir, os.pardir))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "dcf_clone.settings")

import django  # noqa: E402

django.setup()

from apps.data.registry import get_provider  # noqa: E402
from apps.valuation.defaults_epv import derive_epv_defaults  # noqa: E402
from apps.valuation.engine.epv import earnings_power_value  # noqa: E402


TICKERS = ["AAPL", "MSFT", "JNJ", "KO", "WMT", "PLTR"]


def _fmt_b(x: float) -> str:
    """Format a large number in billions with two decimals."""
    try:
        return f"{x / 1e9:>8.2f}B"
    except (TypeError, ValueError):
        return "    n/a"


def _fmt_money(x: float | None) -> str:
    if x is None:
        return "    n/a"
    return f"{x:>10.2f}"


def _fmt_pct(x: float | None) -> str:
    if x is None:
        return "   n/a"
    return f"{x * 100:>+7.2f}%"


def main() -> int:
    provider = get_provider()
    header = (
        f"{'TICKER':<6} "
        f"{'NORM_EBIT':>11} "
        f"{'YRS':>3} "
        f"{'EPV/SHARE':>10} "
        f"{'PRICE':>10} "
        f"{'UPSIDE':>8}"
    )
    print(header)
    print("-" * len(header))

    failures = 0
    for ticker in TICKERS:
        try:
            profile = provider.get_profile(ticker)
            try:
                quote = provider.get_quote(ticker)
            except Exception:
                quote = None
            inputs = derive_epv_defaults(provider, ticker, profile, quote)
            outputs = earnings_power_value(inputs)
            price = getattr(quote, "price", None) if quote else None
            upside = None
            if price:
                upside = (outputs.epv_per_share - price) / price
            print(
                f"{ticker:<6} "
                f"{_fmt_b(inputs.normalized_ebit)} "
                f"{inputs.years_of_history:>3} "
                f"{_fmt_money(outputs.epv_per_share)} "
                f"{_fmt_money(price)} "
                f"{_fmt_pct(upside)}"
            )
        except Exception as e:  # noqa: BLE001
            failures += 1
            print(f"{ticker:<6} ERROR: {e}")
            traceback.print_exc()

    print()
    print(f"{len(TICKERS) - failures}/{len(TICKERS)} succeeded")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
