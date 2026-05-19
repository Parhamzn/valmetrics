"""Live-data self-test for the Simple Excess Return Model.

Bootstraps Django, fetches profile/quote via the data provider, derives default
inputs, runs the engine, and prints a one-line summary per ticker.

Usage::

    .venv/bin/python apps/valuation/tests_excess_return_pages.py

Tickers picked:
    JPM, BAC, WFC, GS, MS  -> core US bank/broker (the model's primary use case)
    AAPL                   -> non-financial control; should still compute
"""

from __future__ import annotations

import os
import sys
import traceback


# --- Path + Django bootstrap ------------------------------------------------

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.abspath(os.path.join(_THIS_DIR, os.pardir, os.pardir))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "valmetrics.settings")

import django  # noqa: E402

django.setup()


from apps.data.registry import get_provider  # noqa: E402
from apps.valuation.defaults_excess_return import (  # noqa: E402
    derive_simple_excess_return_defaults,
)
from apps.valuation.engine.excess_return import simple_excess_return  # noqa: E402


TICKERS = ["JPM", "BAC", "WFC", "GS", "MS", "AAPL"]


def _fmt_pct(x: float | None) -> str:
    if x is None:
        return "    —  "
    return f"{x * 100:+7.2f}%"


def _fmt_money(x: float | None) -> str:
    if x is None:
        return "       —"
    return f"{x:9.2f}"


def main() -> int:
    provider = get_provider()
    print(
        f"{'TICK':<6} {'BV/sh':>10} {'ROE':>9} {'Ke':>8} "
        f"{'g':>8} {'Fair/sh':>10} {'Price':>9} {'Upside':>9}"
    )
    print("-" * 78)

    failures = 0
    for ticker in TICKERS:
        try:
            profile = provider.get_profile(ticker)
            quote = None
            try:
                quote = provider.get_quote(ticker)
            except Exception:  # noqa: BLE001
                quote = None

            inputs = derive_simple_excess_return_defaults(
                provider, ticker, profile, quote
            )

            try:
                outputs = simple_excess_return(inputs)
            except ValueError as e:
                print(
                    f"{ticker:<6} {inputs.book_value_per_share:>10.2f} "
                    f"{_fmt_pct(inputs.return_on_equity):>9} "
                    f"{_fmt_pct(inputs.cost_of_equity):>8} "
                    f"{_fmt_pct(inputs.growth_rate):>8} "
                    f"   ENGINE: {e}"
                )
                continue

            price = quote.price if quote else None
            upside = None
            if price:
                upside = (outputs.fair_value_per_share - price) / price

            print(
                f"{ticker:<6} {inputs.book_value_per_share:>10.2f} "
                f"{_fmt_pct(inputs.return_on_equity)} "
                f"{_fmt_pct(inputs.cost_of_equity)} "
                f"{_fmt_pct(inputs.growth_rate)} "
                f"{_fmt_money(outputs.fair_value_per_share)} "
                f"{_fmt_money(price)} "
                f"{_fmt_pct(upside)}"
            )
        except Exception:  # noqa: BLE001
            failures += 1
            print(f"FAIL {ticker}")
            traceback.print_exc()

    print()
    if failures:
        print(f"{failures} ticker(s) failed unexpectedly")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
