#!/usr/bin/env python
"""Smoke test for the data-provider layer.

Run from the project root:

    .venv/bin/python scripts/smoke_test.py

Exercises YFinanceProvider against AAPL and prints a short summary for
each call. Each call is wrapped in try/except so one upstream hiccup
doesn't mask the others.
"""
from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path

# Make `apps.data` importable when running this file directly.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Try to bring Django up so the cache decorator finds DCF_CACHE_DIR.
# If Django isn't configured yet, cache.py falls back to ~/.dcf_cache/.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "dcf_clone.settings")
try:
    import django  # type: ignore

    django.setup()
    print("[smoke] Django configured.")
except Exception as exc:
    print(f"[smoke] Django not available ({exc}); using ~/.dcf_cache/ fallback.")


def _run(label: str, fn):
    print(f"\n--- {label} ---")
    try:
        return fn()
    except Exception as exc:
        print(f"[ERROR] {label}: {exc}")
        traceback.print_exc(limit=2)
        return None


def main() -> int:
    from apps.data.registry import get_provider

    provider = get_provider()
    ticker = "AAPL"

    def show_profile():
        p = provider.get_profile(ticker)
        print(f"{p.ticker}  {p.name}")
        print(f"  exchange={p.exchange}  currency={p.currency}  country={p.country}")
        print(f"  sector={p.sector}  industry={p.industry}")
        print(f"  employees={p.employees}  market_cap={p.market_cap}")
        print(f"  website={p.website}")
        desc = (p.description or "").strip().replace("\n", " ")
        print(f"  description: {desc[:140]}{'...' if len(desc) > 140 else ''}")

    def show_quote():
        q = provider.get_quote(ticker)
        print(f"{q.ticker} price={q.price} {q.currency}")
        print(f"  change={q.change}  change_pct={q.change_percent}")
        print(f"  market_state={q.market_state}  timestamp={q.timestamp.isoformat()}")

    def show_ratios():
        r = provider.get_ratios(ticker)
        print(f"{r.ticker}")
        for field, value in (
            ("pe", r.pe),
            ("forward_pe", r.forward_pe),
            ("peg", r.peg),
            ("price_to_book", r.price_to_book),
            ("price_to_sales", r.price_to_sales),
            ("ev_to_ebitda", r.ev_to_ebitda),
            ("dividend_yield", r.dividend_yield),
            ("roe", r.return_on_equity),
            ("roa", r.return_on_assets),
            ("debt_to_equity", r.debt_to_equity),
            ("current_ratio", r.current_ratio),
            ("gross_margin", r.gross_margin),
            ("operating_margin", r.operating_margin),
            ("profit_margin", r.profit_margin),
        ):
            print(f"  {field}: {value}")

    def show_income():
        inc = provider.get_income_statement(ticker)
        print(f"{inc.ticker}  currency={inc.currency}  period={inc.period}  rows={len(inc.lines)}")
        for line in inc.lines[:2]:
            print(f"  period_end={line.period_end}  fields={len(line.items)}")
            for k in list(line.items)[:5]:
                print(f"    {k}: {line.items[k]}")

    def show_prices():
        ps = provider.get_price_history(ticker, period="1mo")
        print(f"{ps.ticker}  currency={ps.currency}  points={len(ps.points)}")
        if ps.points:
            first = ps.points[0]
            last = ps.points[-1]
            print(f"  first: {first.date} close={first.close} adj_close={first.adj_close}")
            print(f"  last:  {last.date} close={last.close} adj_close={last.adj_close}")

    _run("get_profile(AAPL)", show_profile)
    _run("get_quote(AAPL)", show_quote)
    _run("get_ratios(AAPL)", show_ratios)
    _run("get_income_statement(AAPL)", show_income)
    _run("get_price_history(AAPL, period='1mo')", show_prices)

    print("\n[smoke] done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
