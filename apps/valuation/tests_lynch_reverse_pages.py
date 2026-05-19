"""Smoke test the Peter Lynch + Reverse DCF flows against real tickers.

Bootstraps Django, derives defaults for a handful of representative
companies, runs both engines, and prints a compact comparison line per
ticker. Designed to be invoked directly::

    .venv/bin/python apps/valuation/tests_lynch_reverse_pages.py
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
from apps.valuation.defaults_peter_lynch import derive_peter_lynch_defaults  # noqa: E402
from apps.valuation.defaults_reverse_dcf import derive_reverse_dcf_defaults  # noqa: E402
from apps.valuation.engine.peter_lynch import peter_lynch_fair_value  # noqa: E402
from apps.valuation.engine.reverse_dcf import reverse_dcf  # noqa: E402


TICKERS = ["AAPL", "MSFT", "NVDA", "KO", "JNJ", "TSLA"]


def _fmt_money(x: float | None) -> str:
    if x is None:
        return "    n/a"
    return f"{x:>10.2f}"


def _fmt_pct(x: float | None) -> str:
    if x is None:
        return "    n/a"
    return f"{x * 100:>+7.2f}%"


def main() -> int:
    provider = get_provider()
    header = (
        f"{'TICKER':<6} "
        f"{'PRICE':>10} "
        f"{'LYNCH_FV':>10} "
        f"{'LYNCH_UPS':>10} "
        f"{'IMPL_G':>8} "
        f"{'CONV':>5} "
        f"{'ITER':>4}"
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
            price = getattr(quote, "price", None) if quote else None

            # --- Peter Lynch ---
            lynch_in = derive_peter_lynch_defaults(provider, ticker, profile, quote)
            lynch_out = peter_lynch_fair_value(lynch_in)
            lynch_upside = None
            if price:
                lynch_upside = (lynch_out.fair_value_per_share - price) / price

            # --- Reverse DCF ---
            rev_in = derive_reverse_dcf_defaults(provider, ticker, profile, quote)
            if rev_in is None:
                impl_g = None
                conv = "n/a"
                iters = 0
            else:
                rev_out = reverse_dcf(rev_in)
                impl_g = rev_out.implied_revenue_growth
                conv = "yes" if rev_out.converged else "no"
                iters = rev_out.iterations

            print(
                f"{ticker:<6} "
                f"{_fmt_money(price)} "
                f"{_fmt_money(lynch_out.fair_value_per_share)} "
                f"{_fmt_pct(lynch_upside)} "
                f"{_fmt_pct(impl_g)} "
                f"{conv:>5} "
                f"{iters:>4}"
            )
            if lynch_out.warning:
                print(f"       lynch warn: {lynch_out.warning}")
            if rev_in is not None and rev_out.warning:
                print(f"       reverse warn: {rev_out.warning}")
        except Exception as e:  # noqa: BLE001
            failures += 1
            print(f"{ticker:<6} ERROR: {e}")
            traceback.print_exc()

    print()
    print(f"{len(TICKERS) - failures}/{len(TICKERS)} succeeded")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
