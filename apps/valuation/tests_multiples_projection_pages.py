"""Smoke test the two multiples-valuation flows against real tickers.

Bootstraps Django, derives defaults for a handful of representative companies,
runs both engines (DCF — Exit Multiple, Discounted Future Market Cap), and
prints a compact comparison line per ticker. Designed to be invoked directly::

    .venv/bin/python apps/valuation/tests_multiples_projection_pages.py
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
from apps.valuation.defaults_dcf_exit_multiple import (  # noqa: E402
    derive_dcf_exit_multiple_defaults,
)
from apps.valuation.defaults_discounted_future_mcap import (  # noqa: E402
    derive_dfmc_defaults,
)
from apps.valuation.engine.dcf_exit_multiple import dcf_exit_multiple  # noqa: E402
from apps.valuation.engine.discounted_future_mcap import (  # noqa: E402
    discounted_future_mcap,
)


TICKERS = ["AAPL", "MSFT", "NVDA", "BRK-B", "KO"]


def _fmt_money(x: float | None) -> str:
    if x is None:
        return "    n/a"
    return f"{x:>10.2f}"


def _fmt_pct(x: float | None) -> str:
    if x is None:
        return "   n/a"
    return f"{x * 100:>+7.2f}%"


def _safe_quote(provider, ticker):
    try:
        return provider.get_quote(ticker)
    except Exception:  # noqa: BLE001
        return None


def _upside(fv: float | None, price: float | None) -> float | None:
    if fv is None or not price:
        return None
    return (fv - price) / price


def main() -> int:
    provider = get_provider()

    # ----------------------------- Exit Multiple ----------------------------
    header_em = (
        f"{'TICKER':<6} "
        f"{'EXIT_MULT':>9} "
        f"{'IMPL_G':>7} "
        f"{'FV/SH':>10} "
        f"{'PRICE':>10} "
        f"{'UPSIDE':>8}"
    )
    print("== DCF — Exit Multiple ==")
    print(header_em)
    print("-" * len(header_em))

    failures = 0
    for ticker in TICKERS:
        try:
            profile = provider.get_profile(ticker)
            quote = _safe_quote(provider, ticker)
            inputs = derive_dcf_exit_multiple_defaults(provider, ticker, profile, quote)
            outputs = dcf_exit_multiple(inputs)
            price = getattr(quote, "price", None) if quote else None
            upside = _upside(outputs.fair_value_per_share, price)
            print(
                f"{ticker:<6} "
                f"{inputs.exit_ev_ebitda:>8.2f}x "
                f"{_fmt_pct(outputs.implied_terminal_growth)} "
                f"{_fmt_money(outputs.fair_value_per_share)} "
                f"{_fmt_money(price)} "
                f"{_fmt_pct(upside)}"
            )
        except Exception as e:  # noqa: BLE001
            failures += 1
            print(f"{ticker:<6} ERROR: {e}")
            traceback.print_exc()

    # ----------------------- Discounted Future Market Cap -------------------
    header_dfmc = (
        f"{'TICKER':<6} "
        f"{'BASE_NI':>12} "
        f"{'GROWTH':>7} "
        f"{'TERM_PE':>8} "
        f"{'FV/SH':>10} "
        f"{'PRICE':>10} "
        f"{'UPSIDE':>8}"
    )
    print()
    print("== Discounted Future Market Cap ==")
    print(header_dfmc)
    print("-" * len(header_dfmc))

    for ticker in TICKERS:
        try:
            profile = provider.get_profile(ticker)
            quote = _safe_quote(provider, ticker)
            inputs = derive_dfmc_defaults(provider, ticker, profile, quote)
            outputs = discounted_future_mcap(inputs)
            price = getattr(quote, "price", None) if quote else None
            upside = _upside(outputs.fair_value_per_share, price)
            base_ni_b = (
                f"{inputs.base_net_income / 1e9:>11.2f}B"
                if inputs.base_net_income is not None
                else "         n/a"
            )
            print(
                f"{ticker:<6} "
                f"{base_ni_b} "
                f"{_fmt_pct(inputs.net_income_growth_rate)} "
                f"{inputs.terminal_pe:>7.2f}x "
                f"{_fmt_money(outputs.fair_value_per_share)} "
                f"{_fmt_money(price)} "
                f"{_fmt_pct(upside)}"
            )
        except Exception as e:  # noqa: BLE001
            failures += 1
            print(f"{ticker:<6} ERROR: {e}")
            traceback.print_exc()

    print()
    print(f"failures: {failures}")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
