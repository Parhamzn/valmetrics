"""Smoke test the CAPM and WACC flows against real tickers.

Bootstraps Django, derives defaults for a handful of representative
companies, runs the engine, and prints a compact line per ticker. Designed
to be invoked directly::

    .venv/bin/python apps/valuation/tests_cost_of_capital_pages.py
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

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "valmetrics.settings")

import django  # noqa: E402

django.setup()

from apps.data.registry import get_provider  # noqa: E402
from apps.valuation.defaults_capm import derive_capm_defaults  # noqa: E402
from apps.valuation.defaults_wacc import derive_wacc_defaults  # noqa: E402
from apps.valuation.engine.capm import capm_cost_of_equity  # noqa: E402
from apps.valuation.engine.wacc import wacc  # noqa: E402


TICKERS = ["AAPL", "MSFT", "JPM", "VZ", "TSLA", "NVDA", "BRK-B"]


def _fmt_pct(x: float | None) -> str:
    if x is None:
        return "    n/a"
    return f"{x * 100:>7.2f}%"


def _fmt_b(x: float | None) -> str:
    if x is None:
        return "    n/a"
    try:
        return f"{x / 1e9:>8.2f}B"
    except (TypeError, ValueError):
        return "    n/a"


def _fmt_beta(x: float | None) -> str:
    if x is None:
        return "  n/a"
    return f"{x:>5.2f}"


def _run_capm(provider, ticker, profile, quote) -> int:
    """Run CAPM for one ticker; return 0 on success, 1 on failure."""
    try:
        inputs = derive_capm_defaults(provider, ticker, profile, quote)
        outputs = capm_cost_of_equity(inputs)
        print(
            f"  CAPM  rf={_fmt_pct(inputs.risk_free_rate)}  "
            f"beta={_fmt_beta(inputs.beta)}  "
            f"erp={_fmt_pct(inputs.equity_risk_premium)}  "
            f"->  Ke={_fmt_pct(outputs.cost_of_equity)}"
        )
        return 0
    except Exception as e:  # noqa: BLE001
        print(f"  CAPM  ERROR: {e}")
        traceback.print_exc()
        return 1


def _run_wacc(provider, ticker, profile, quote) -> int:
    """Run WACC for one ticker; return 0 on success, 1 on failure."""
    try:
        inputs = derive_wacc_defaults(provider, ticker, profile, quote)
        outputs = wacc(inputs)
        print(
            f"  WACC  Ke={_fmt_pct(inputs.cost_of_equity)}  "
            f"Kd={_fmt_pct(inputs.cost_of_debt)}  "
            f"t={_fmt_pct(inputs.tax_rate)}  "
            f"MVE={_fmt_b(inputs.market_value_equity)}  "
            f"MVD={_fmt_b(inputs.market_value_debt)}  "
            f"->  WACC={_fmt_pct(outputs.wacc)}  "
            f"(E={_fmt_pct(outputs.equity_weight)}, "
            f"D={_fmt_pct(outputs.debt_weight)})"
        )
        return 0
    except Exception as e:  # noqa: BLE001
        print(f"  WACC  ERROR: {e}")
        traceback.print_exc()
        return 1


def main() -> int:
    provider = get_provider()
    failures = 0

    for ticker in TICKERS:
        print(f"\n=== {ticker} ===")
        try:
            profile = provider.get_profile(ticker)
        except Exception as e:  # noqa: BLE001
            print(f"  ERROR fetching profile: {e}")
            failures += 1
            continue

        try:
            quote = provider.get_quote(ticker)
        except Exception:  # noqa: BLE001
            quote = None

        failures += _run_capm(provider, ticker, profile, quote)
        failures += _run_wacc(provider, ticker, profile, quote)

    total_runs = len(TICKERS) * 2
    print()
    print(f"{total_runs - failures}/{total_runs} runs succeeded")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
