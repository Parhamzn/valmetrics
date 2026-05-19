"""Tests for the ROIC engine.

Pytest-compatible (plain ``assert`` and ``def test_*``). Also runnable as a
script::

    python apps/valuation/engine/tests_roic.py
"""

from __future__ import annotations

import os
import sys

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.abspath(os.path.join(_THIS_DIR, os.pardir, os.pardir, os.pardir))
sys.path[:] = [p for p in sys.path if os.path.abspath(p or ".") != _THIS_DIR]
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import traceback  # noqa: E402
from dataclasses import dataclass  # noqa: E402
from datetime import date  # noqa: E402

from apps.valuation.engine.roic import compute_roic  # noqa: E402
from apps.valuation.engine.types_roic import ROICInputs  # noqa: E402


@dataclass
class FakeLine:
    period_end: date
    items: dict


def _pair(year, *, ebit=None, op=None, tax_rate=None, equity=None,
          ltd=None, cd=None, cash=None, net_income=None,
          tax_provision=None, pretax_income=None):
    """Build a (income_line, balance_line) pair for one fiscal year."""
    income = FakeLine(
        period_end=date(year, 12, 31),
        items={
            "ebit": ebit,
            "operating_income": op,
            "tax_rate_for_calcs": tax_rate,
            "net_income": net_income,
            "tax_provision": tax_provision,
            "pretax_income": pretax_income,
        },
    )
    balance = FakeLine(
        period_end=date(year, 12, 31),
        items={
            "common_stock_equity": equity,
            "long_term_debt": ltd,
            "current_debt": cd,
            "cash_and_cash_equivalents": cash,
        },
    )
    return (income, balance)


# ---------------------------------------------------------------------------
# Hand-computed example
# ---------------------------------------------------------------------------


def test_roic_basic_hand_computed() -> None:
    """One-year example with simple round numbers.

    EBIT = 200, tax = 0.20 -> NOPAT = 160
    Equity = 500, LTD = 200, CD = 100, Cash = 100
    Invested capital = 500 + 200 + 100 - 100 = 700
    ROIC = 160 / 700 ~= 0.22857...
    """
    pairs = [
        _pair(2024, ebit=200.0, tax_rate=0.20, equity=500.0, ltd=200.0, cd=100.0, cash=100.0),
    ]
    out = compute_roic(ROICInputs(ticker="HC", annual_periods=pairs))

    assert len(out.points) == 1
    p = out.points[0]
    assert abs(p.nopat - 160.0) < 1e-9, p.nopat
    assert abs(p.invested_capital - 700.0) < 1e-9, p.invested_capital
    assert abs(p.roic - (160.0 / 700.0)) < 1e-12, p.roic
    # Latest = only entry, ROIC ~22.9% > 8% WACC -> creates value.
    assert out.creates_value is True
    # <3 points -> insufficient data.
    assert out.trend == "insufficient data"


def test_roic_tax_rate_derived_from_provision() -> None:
    """When tax_rate_for_calcs is absent, fall back to provision/pretax."""
    # tax_provision/pretax = 21/100 = 0.21 -> NOPAT = 100 * 0.79 = 79
    pairs = [
        _pair(2024,
              ebit=100.0, tax_rate=None,
              tax_provision=21.0, pretax_income=100.0,
              equity=500.0, ltd=200.0, cd=100.0, cash=100.0),
    ]
    out = compute_roic(ROICInputs(ticker="TX", annual_periods=pairs))
    p = out.points[0]
    assert abs(p.nopat - 79.0) < 1e-9, p.nopat


def test_roic_tax_rate_fallback_constant() -> None:
    """No tax info anywhere -> 21% fallback."""
    pairs = [
        _pair(2024, ebit=100.0, equity=500.0, ltd=200.0, cd=100.0, cash=100.0),
    ]
    out = compute_roic(ROICInputs(ticker="FB", annual_periods=pairs))
    # NOPAT = 100 * (1 - 0.21) = 79
    assert abs(out.points[0].nopat - 79.0) < 1e-9


def test_roic_ebit_fallback_to_operating_income() -> None:
    """Missing EBIT but present operating_income -> use the latter."""
    pairs = [
        _pair(2024, ebit=None, op=200.0, tax_rate=0.20,
              equity=500.0, ltd=200.0, cd=100.0, cash=100.0),
    ]
    out = compute_roic(ROICInputs(ticker="OP", annual_periods=pairs))
    p = out.points[0]
    assert abs(p.nopat - 160.0) < 1e-9, p.nopat


# ---------------------------------------------------------------------------
# Trend cases
# ---------------------------------------------------------------------------


def test_roic_clearly_expanding_trend() -> None:
    """ROIC rises ~3 pts per year -> 'expanding'."""
    # Hold invested capital fixed, vary EBIT.
    base_ic = dict(equity=600.0, ltd=300.0, cd=100.0, cash=0.0)  # IC = 1000
    pairs = [
        _pair(2020, ebit=80.0, tax_rate=0.0, **base_ic),   # ROIC 0.08
        _pair(2021, ebit=110.0, tax_rate=0.0, **base_ic),  # 0.11
        _pair(2022, ebit=140.0, tax_rate=0.0, **base_ic),  # 0.14
        _pair(2023, ebit=170.0, tax_rate=0.0, **base_ic),  # 0.17
        _pair(2024, ebit=200.0, tax_rate=0.0, **base_ic),  # 0.20
    ]
    out = compute_roic(ROICInputs(ticker="EXP", annual_periods=pairs))
    assert out.trend == "expanding", out.trend
    # Avg ROIC = mean(0.08..0.20) = 0.14.
    assert abs(out.avg_roic - 0.14) < 1e-9, out.avg_roic
    # Latest 0.20 > 0.08 WACC -> creates value.
    assert out.creates_value is True
    # Oldest-first ordering check.
    assert out.points[0].period_end == date(2020, 12, 31)
    assert out.points[-1].period_end == date(2024, 12, 31)


def test_roic_clearly_compressing_trend() -> None:
    """ROIC slides hard -> 'compressing', and may stop creating value."""
    base_ic = dict(equity=600.0, ltd=300.0, cd=100.0, cash=0.0)  # IC = 1000
    pairs = [
        _pair(2020, ebit=200.0, tax_rate=0.0, **base_ic),  # 0.20
        _pair(2021, ebit=160.0, tax_rate=0.0, **base_ic),  # 0.16
        _pair(2022, ebit=120.0, tax_rate=0.0, **base_ic),  # 0.12
        _pair(2023, ebit=80.0, tax_rate=0.0, **base_ic),   # 0.08
        _pair(2024, ebit=40.0, tax_rate=0.0, **base_ic),   # 0.04
    ]
    out = compute_roic(ROICInputs(ticker="CMP", annual_periods=pairs))
    assert out.trend == "compressing", out.trend
    # WACC 0.08, latest 0.04 -> destroys value.
    assert out.creates_value is False


def test_roic_stable_trend() -> None:
    """Small noise inside the 50 bps band -> 'stable'."""
    base_ic = dict(equity=600.0, ltd=300.0, cd=100.0, cash=0.0)
    pairs = [
        _pair(2020, ebit=100.0, tax_rate=0.0, **base_ic),  # 0.10
        _pair(2021, ebit=101.0, tax_rate=0.0, **base_ic),
        _pair(2022, ebit=99.0, tax_rate=0.0, **base_ic),
        _pair(2023, ebit=100.5, tax_rate=0.0, **base_ic),
        _pair(2024, ebit=100.0, tax_rate=0.0, **base_ic),
    ]
    out = compute_roic(ROICInputs(ticker="STB", annual_periods=pairs))
    assert out.trend == "stable", out.trend


# ---------------------------------------------------------------------------
# Missing-data handling
# ---------------------------------------------------------------------------


def test_roic_missing_ebit_yields_none_nopat() -> None:
    pairs = [
        _pair(2024, ebit=None, op=None, equity=500.0, ltd=200.0, cd=100.0, cash=100.0),
    ]
    out = compute_roic(ROICInputs(ticker="MISS", annual_periods=pairs))
    p = out.points[0]
    assert p.nopat is None
    assert p.roic is None
    assert out.creates_value is None


def test_roic_negative_invested_capital() -> None:
    """Negative book equity + tiny debt + huge cash -> non-positive IC; ROIC None."""
    pairs = [
        _pair(2024, ebit=100.0, tax_rate=0.20,
              equity=-100.0, ltd=10.0, cd=0.0, cash=200.0),
        # IC = -100 + 10 + 0 - 200 = -290 -> skipped.
    ]
    out = compute_roic(ROICInputs(ticker="NEG", annual_periods=pairs))
    p = out.points[0]
    assert p.nopat is not None
    assert p.invested_capital is not None
    assert p.invested_capital < 0
    assert p.roic is None, p.roic


def test_roic_wacc_override_changes_value_verdict() -> None:
    """Override wacc_estimate: a high WACC flips creates_value to False."""
    pairs = [
        _pair(2024, ebit=200.0, tax_rate=0.20,
              equity=500.0, ltd=200.0, cd=100.0, cash=100.0),
    ]
    # ROIC ~= 22.86%
    high = compute_roic(ROICInputs(ticker="W", annual_periods=pairs, wacc_estimate=0.30))
    low = compute_roic(ROICInputs(ticker="W", annual_periods=pairs, wacc_estimate=0.05))
    assert high.creates_value is False
    assert low.creates_value is True


def test_roic_empty_input() -> None:
    out = compute_roic(ROICInputs(ticker="E", annual_periods=[]))
    assert out.points == []
    assert out.avg_roic is None
    assert out.creates_value is None
    assert out.trend == "insufficient data"


# ---------------------------------------------------------------------------
# Script entrypoint
# ---------------------------------------------------------------------------


def _run_all() -> int:
    tests = [
        (name, obj)
        for name, obj in sorted(globals().items())
        if name.startswith("test_") and callable(obj)
    ]
    failures = 0
    for name, fn in tests:
        try:
            fn()
        except Exception:  # noqa: BLE001
            failures += 1
            print(f"FAIL {name}")
            traceback.print_exc()
        else:
            print(f"PASS {name}")
    print()
    print(f"{len(tests) - failures}/{len(tests)} passed")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(_run_all())
