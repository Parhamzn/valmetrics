"""Smoke test the EV/EBITDA and EV/Sales multiples flows against real tickers.

Bootstraps Django, derives defaults for a mix of profitable / barely profitable
/ high-growth / unprofitable companies, runs both engines, and prints a compact
comparison line per ticker.

The mix is deliberate: ``BIIB`` and ``PLTR`` are useful to demonstrate that
EV/EBITDA can fail (or produce odd numbers) on companies with weak / negative
EBITDA, while EV/Sales handles them gracefully.

Invoke directly::

    .venv/bin/python apps/valuation/tests_ev_multiples_pages.py
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
from apps.valuation.defaults_ev_ebitda import derive_ev_ebitda_defaults  # noqa: E402
from apps.valuation.defaults_ev_sales import derive_ev_sales_defaults  # noqa: E402
from apps.valuation.engine.ev_ebitda import ev_ebitda_valuation  # noqa: E402
from apps.valuation.engine.ev_sales import ev_sales_valuation  # noqa: E402


TICKERS = ["AAPL", "MSFT", "NVDA", "BIIB", "SHOP", "PLTR", "TSLA"]


def _fmt_b(x: float | None) -> str:
    """Format a large number in billions with two decimals."""
    if x is None:
        return "      n/a"
    try:
        return f"{x / 1e9:>8.2f}B"
    except (TypeError, ValueError):
        return "      n/a"


def _fmt_money(x: float | None) -> str:
    if x is None:
        return "    n/a"
    return f"{x:>10.2f}"


def _fmt_pct(x: float | None) -> str:
    if x is None:
        return "    n/a"
    return f"{x * 100:>+7.2f}%"


def _fmt_mult(x: float | None) -> str:
    if x is None:
        return "  n/a "
    return f"{x:>6.2f}x"


def _compute_current_ev_multiple(profile, denominator: float, net_debt: float) -> float | None:
    if profile is None or denominator is None or denominator <= 0:
        return None
    mc = getattr(profile, "market_cap", None)
    if mc is None:
        return None
    try:
        return (float(mc) + float(net_debt)) / float(denominator)
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def _run_ev_ebitda(provider) -> int:
    print("\n=== EV / EBITDA ===")
    header = (
        f"{'TICKER':<6} "
        f"{'EBITDA':>10} "
        f"{'TARGET':>7} "
        f"{'CURRENT':>8} "
        f"{'FAIR/SH':>10} "
        f"{'PRICE':>10} "
        f"{'UPSIDE':>9}"
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
            inputs = derive_ev_ebitda_defaults(provider, ticker, profile, quote)
            current_mult = _compute_current_ev_multiple(profile, inputs.ebitda, inputs.net_debt)
            try:
                outputs = ev_ebitda_valuation(inputs, current_multiple=current_mult)
                price = getattr(quote, "price", None) if quote else None
                upside = None
                if price:
                    upside = (outputs.fair_value_per_share - price) / price
                print(
                    f"{ticker:<6} "
                    f"{_fmt_b(inputs.ebitda)} "
                    f"{_fmt_mult(inputs.target_ev_ebitda)} "
                    f"{_fmt_mult(current_mult)} "
                    f"{_fmt_money(outputs.fair_value_per_share)} "
                    f"{_fmt_money(price)} "
                    f"{_fmt_pct(upside)}"
                )
            except ValueError as ve:
                # Expected for negative-EBITDA tickers — demonstrate the guard.
                print(
                    f"{ticker:<6} "
                    f"{_fmt_b(inputs.ebitda)} "
                    f"  SKIP   (EV/EBITDA not applicable: {ve})"
                )
        except Exception as e:  # noqa: BLE001
            failures += 1
            print(f"{ticker:<6} ERROR: {e}")
            traceback.print_exc()
    return failures


def _run_ev_sales(provider) -> int:
    print("\n=== EV / Sales ===")
    header = (
        f"{'TICKER':<6} "
        f"{'REVENUE':>10} "
        f"{'TARGET':>7} "
        f"{'CURRENT':>8} "
        f"{'FAIR/SH':>10} "
        f"{'PRICE':>10} "
        f"{'UPSIDE':>9}"
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
            inputs = derive_ev_sales_defaults(provider, ticker, profile, quote)
            current_mult = _compute_current_ev_multiple(profile, inputs.revenue, inputs.net_debt)
            outputs = ev_sales_valuation(inputs, current_multiple=current_mult)
            price = getattr(quote, "price", None) if quote else None
            upside = None
            if price:
                upside = (outputs.fair_value_per_share - price) / price
            print(
                f"{ticker:<6} "
                f"{_fmt_b(inputs.revenue)} "
                f"{_fmt_mult(inputs.target_ev_sales)} "
                f"{_fmt_mult(current_mult)} "
                f"{_fmt_money(outputs.fair_value_per_share)} "
                f"{_fmt_money(price)} "
                f"{_fmt_pct(upside)}"
            )
        except Exception as e:  # noqa: BLE001
            failures += 1
            print(f"{ticker:<6} ERROR: {e}")
            traceback.print_exc()
    return failures


def main() -> int:
    provider = get_provider()
    f1 = _run_ev_ebitda(provider)
    f2 = _run_ev_sales(provider)
    total = f1 + f2
    print()
    print(f"{2 * len(TICKERS) - total}/{2 * len(TICKERS)} succeeded")
    return 0 if total == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
