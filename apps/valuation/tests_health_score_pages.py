"""Smoke test the Piotroski F-Score + Altman Z-Score flows against real tickers.

Bootstraps Django, derives defaults for a mix of healthy and capital-intensive
/ cyclical companies, runs both engines, and prints a compact diagnostic
block per ticker. Designed to be invoked directly::

    .venv/bin/python apps/valuation/tests_health_score_pages.py
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
from apps.valuation.defaults_altman import derive_altman_defaults  # noqa: E402
from apps.valuation.defaults_piotroski import derive_piotroski_defaults  # noqa: E402
from apps.valuation.engine.altman import altman_z_score  # noqa: E402
from apps.valuation.engine.piotroski import piotroski_f_score  # noqa: E402


# Mix of healthy mega-caps + capital-intensive / cyclical names.
TICKERS = ["AAPL", "MSFT", "NVDA", "F", "CCL", "AAL"]


def _fmt_ratio(x):
    if x is None:
        return "n/a"
    return f"{x:>7.3f}"


def main() -> int:
    provider = get_provider()
    failures = 0

    for ticker in TICKERS:
        print("=" * 72)
        print(f"TICKER: {ticker}")
        print("-" * 72)

        try:
            profile = provider.get_profile(ticker)
        except Exception as e:  # noqa: BLE001
            failures += 1
            print(f"  Could not fetch profile: {e}")
            continue

        try:
            quote = provider.get_quote(ticker)
        except Exception:  # noqa: BLE001
            quote = None

        # --- Piotroski ----------------------------------------------------
        try:
            pinputs = derive_piotroski_defaults(provider, ticker, profile, quote)
            pout = piotroski_f_score(pinputs)
            print(f"  Piotroski F-Score: {pout.total_score}/9  -- {pout.classification}")
            failed = [
                f"#{i + 1} {c.name}" for i, c in enumerate(pout.criteria) if c.score == 0
            ]
            if failed:
                print(f"    Failed criteria: {', '.join(failed)}")
            else:
                print("    All 9 criteria passed")
        except Exception as e:  # noqa: BLE001
            failures += 1
            print(f"  Piotroski ERROR: {e}")
            traceback.print_exc()

        # --- Altman --------------------------------------------------------
        try:
            ainputs = derive_altman_defaults(provider, ticker, profile, quote)
            aout = altman_z_score(ainputs)
            print(
                f"  Altman Z-Score:   {aout.z_score:>7.3f}     -- {aout.zone}"
            )
            labels = ["A", "B", "C", "D", "E"]
            for label, c in zip(labels, aout.components):
                print(
                    f"    {label} {c.name:<48} "
                    f"ratio={_fmt_ratio(c.ratio)} "
                    f"weighted={_fmt_ratio(c.weighted)}"
                )
            if aout.warning:
                print(f"    Warning: {aout.warning}")
        except Exception as e:  # noqa: BLE001
            failures += 1
            print(f"  Altman ERROR: {e}")
            traceback.print_exc()

    print("=" * 72)
    print(f"{len(TICKERS)} tickers processed, {failures} errors")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
