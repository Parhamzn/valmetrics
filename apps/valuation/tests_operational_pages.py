"""Smoke test the two operational pages against real tickers.

Bootstraps Django, derives defaults for a varied set of companies, runs the
Margin Analysis + ROIC engines, and prints a compact one-line summary per
ticker. Designed to be invoked directly::

    .venv/bin/python apps/valuation/tests_operational_pages.py

Ticker mix is deliberately varied across margin profiles:
    AAPL / MSFT / NVDA   high-margin tech
    T                    telecom (capital intensive, lower margin)
    F                    auto (cyclical, thin margin)
    WMT                  retail (very thin margin, high turnover)
"""

from __future__ import annotations

import os
import sys
import traceback

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.abspath(os.path.join(_THIS_DIR, os.pardir, os.pardir))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "valmetrics.settings")

import django  # noqa: E402

django.setup()

from apps.data.registry import get_provider  # noqa: E402
from apps.valuation.defaults_margin_analysis import (  # noqa: E402
    derive_margin_analysis_defaults,
)
from apps.valuation.defaults_roic import derive_roic_defaults  # noqa: E402
from apps.valuation.engine.margin_analysis import margin_analysis  # noqa: E402
from apps.valuation.engine.roic import compute_roic  # noqa: E402


TICKERS = ["AAPL", "MSFT", "NVDA", "T", "F", "WMT"]


def _fmt_pct(x):
    if x is None:
        return "   n/a"
    return f"{x * 100:>+7.2f}%"


def _fmt_bool(x):
    if x is True:
        return "YES"
    if x is False:
        return " no"
    return "  ?"


def main() -> int:
    provider = get_provider()
    failures = 0

    # ---------------- Margin Analysis ---------------------------------------
    print("== Margin Analysis ==")
    header = (
        f"{'TICKER':<6} "
        f"{'AVG_GM':>8} "
        f"{'AVG_OM':>8} "
        f"{'AVG_NM':>8} "
        f"{'TREND_G':>11} "
        f"{'TREND_O':>11} "
        f"{'TREND_N':>11}"
    )
    print(header)
    print("-" * len(header))
    for ticker in TICKERS:
        try:
            inputs = derive_margin_analysis_defaults(provider, ticker)
            out = margin_analysis(inputs)
            print(
                f"{ticker:<6} "
                f"{_fmt_pct(out.avg_gross_margin)} "
                f"{_fmt_pct(out.avg_operating_margin)} "
                f"{_fmt_pct(out.avg_profit_margin)} "
                f"{out.trend_gross:>11} "
                f"{out.trend_operating:>11} "
                f"{out.trend_profit:>11}"
            )
        except Exception as e:  # noqa: BLE001
            failures += 1
            print(f"{ticker:<6} ERROR: {e}")
            traceback.print_exc()

    # ---------------- ROIC --------------------------------------------------
    print()
    print("== ROIC ==")
    header = (
        f"{'TICKER':<6} "
        f"{'AVG_ROIC':>9} "
        f"{'LATEST':>9} "
        f"{'TREND':>11} "
        f"{'WACC':>8} "
        f"{'CREATES':>8}"
    )
    print(header)
    print("-" * len(header))
    for ticker in TICKERS:
        try:
            inputs = derive_roic_defaults(provider, ticker)
            out = compute_roic(inputs)
            print(
                f"{ticker:<6} "
                f"{_fmt_pct(out.avg_roic)} "
                f"{_fmt_pct(out.latest.roic)} "
                f"{out.trend:>11} "
                f"{_fmt_pct(out.wacc_estimate)} "
                f"{_fmt_bool(out.creates_value):>8}"
            )
        except Exception as e:  # noqa: BLE001
            failures += 1
            print(f"{ticker:<6} ERROR: {e}")
            traceback.print_exc()

    print()
    print(f"{(2 * len(TICKERS)) - failures}/{2 * len(TICKERS)} succeeded")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
