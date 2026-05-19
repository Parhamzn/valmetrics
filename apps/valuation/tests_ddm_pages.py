#!/usr/bin/env python
"""Smoke test: imports defaults_ddm + engine, derives defaults for a few
tickers, runs the engine, prints results.

Run from project root:

    .venv/bin/python apps/valuation/tests_ddm_pages.py

Bootstrap mirrors ``scripts/smoke_test.py``. This file is intentionally
outside ``apps/valuation/engine/`` because it touches the data layer and
Django.
"""
from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path

# Make the project importable when this file is run directly.
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "valmetrics.settings")
try:
    import django  # type: ignore

    django.setup()
    print("[ddm-smoke] Django configured.")
except Exception as exc:  # pragma: no cover
    print(f"[ddm-smoke] Django not available ({exc}); continuing.")


TICKERS = ["KO", "JNJ", "VZ", "PG", "NVDA", "BRK-B"]


def _fmt(value, places=4):
    if value is None:
        return "None"
    try:
        return f"{float(value):.{places}f}"
    except (TypeError, ValueError):
        return str(value)


def _run_for_ticker(provider, ticker: str) -> None:
    from apps.valuation.defaults_ddm import (
        derive_simple_ddm_defaults,
        derive_two_stage_ddm_defaults,
    )
    from apps.valuation.engine.ddm import simple_ddm, two_stage_ddm

    print(f"\n===== {ticker} =====")

    # Profile / quote (best-effort).
    profile = None
    quote = None
    try:
        profile = provider.get_profile(ticker)
        print(f"  name: {profile.name}  currency: {profile.currency}")
    except Exception as exc:
        print(f"  [WARN] get_profile failed: {exc}")
    try:
        quote = provider.get_quote(ticker)
        print(f"  price: {quote.currency} {_fmt(quote.price, 2)}")
    except Exception as exc:
        print(f"  [WARN] get_quote failed: {exc}")

    price = getattr(quote, "price", None)

    # --- Simple DDM -----------------------------------------------------
    try:
        s_inputs = derive_simple_ddm_defaults(provider, ticker, profile, quote)
        print(
            f"  [Simple DDM] D0={_fmt(s_inputs.current_dividend)} "
            f"g={_fmt(s_inputs.growth_rate)} r={_fmt(s_inputs.required_return)}"
        )
        s_out = simple_ddm(s_inputs)
        if price:
            upside = (s_out.fair_value - price) / price
            print(
                f"    fair_value={_fmt(s_out.fair_value, 2)}  "
                f"upside={_fmt(upside * 100, 2)}%"
            )
        else:
            print(f"    fair_value={_fmt(s_out.fair_value, 2)}  upside=N/A")
    except Exception as exc:
        print(f"    ERROR (Simple DDM): {exc}")
        traceback.print_exc(limit=1)

    # --- Two-Stage DDM --------------------------------------------------
    try:
        t_inputs = derive_two_stage_ddm_defaults(provider, ticker, profile, quote)
        print(
            f"  [Two-Stage DDM] D0={_fmt(t_inputs.current_dividend)} "
            f"g1={_fmt(t_inputs.high_growth_rate)} N={t_inputs.high_growth_years} "
            f"g2={_fmt(t_inputs.terminal_growth_rate)} r={_fmt(t_inputs.required_return)}"
        )
        t_out = two_stage_ddm(t_inputs)
        if price:
            upside = (t_out.fair_value - price) / price
            print(
                f"    fair_value={_fmt(t_out.fair_value, 2)}  "
                f"upside={_fmt(upside * 100, 2)}%  "
                f"TV={_fmt(t_out.terminal_value, 2)}  "
                f"PV(TV)={_fmt(t_out.pv_terminal_value, 2)}"
            )
        else:
            print(
                f"    fair_value={_fmt(t_out.fair_value, 2)}  upside=N/A  "
                f"TV={_fmt(t_out.terminal_value, 2)}"
            )
    except Exception as exc:
        print(f"    ERROR (Two-Stage DDM): {exc}")
        traceback.print_exc(limit=1)


def main() -> int:
    from apps.data.registry import get_provider

    provider = get_provider()
    for ticker in TICKERS:
        try:
            _run_for_ticker(provider, ticker)
        except Exception as exc:  # outer guard so one bad ticker doesn't stop us
            print(f"\n===== {ticker} =====\n  ERROR (outer): {exc}")
            traceback.print_exc(limit=2)

    print("\n[ddm-smoke] done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
