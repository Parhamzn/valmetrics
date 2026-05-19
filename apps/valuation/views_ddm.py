"""Views for the Dividend Discount Models (Simple Gordon, Two-Stage).

Mirrors :func:`apps.valuation.views.dcf_pg_view` exactly in render modes:

* ``?partial=results``        -> results pane only (htmx form swap)
* htmx request, no ``partial`` -> tab body fragment
* neither                      -> full HTML page

The parent ``apps.valuation.views`` module will import ``simple_ddm_view``
and ``two_stage_ddm_view`` and wire URL routes during integration.
"""

from __future__ import annotations

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET

from apps.companies.views import _base_ctx, _render_tab
from apps.data.base import DataProviderError  # noqa: F401  (kept for parity)
from apps.data.registry import get_provider
from apps.valuation.defaults_ddm import (
    apply_simple_ddm_overrides,
    apply_two_stage_ddm_overrides,
    derive_simple_ddm_defaults,
    derive_two_stage_ddm_defaults,
)
from apps.valuation.engine.ddm import simple_ddm, two_stage_ddm


def _dividend_warning(provider, ticker: str) -> str | None:
    """Return a warning string if the company has no recent dividend payments."""
    from datetime import date, timedelta
    try:
        divs = provider.get_dividends(ticker)
    except DataProviderError:
        return None
    if not divs:
        return "This company pays no dividend; DDM is not applicable."
    cutoff = date.today() - timedelta(days=730)
    if not any(d.date >= cutoff for d in divs):
        return "This company has not paid a dividend in the last 2 years; DDM is not applicable."
    return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _upside_pct(fair_value: float | None, quote) -> float | None:
    """Compute (fair - price) / price, returning None on missing inputs."""
    if fair_value is None or quote is None:
        return None
    price = getattr(quote, "price", None)
    if not price:
        return None
    return (fair_value - price) / price


# ---------------------------------------------------------------------------
# Views
# ---------------------------------------------------------------------------


@require_GET
def simple_ddm_view(request: HttpRequest, ticker: str) -> HttpResponse:
    """Render the Simple (Gordon) Dividend Discount Model page."""
    ctx, early = _base_ctx(request, ticker)
    if early is not None:
        return early
    ctx["active_tab"] = "models"

    provider = get_provider()

    # Defaults: surface the "no recent dividend" warning *before* user
    # overrides so it reflects the underlying data, not the form input.
    defaults = derive_simple_ddm_defaults(
        provider, ctx["ticker"], ctx["profile"], ctx["quote"]
    )
    dividend_warning = _dividend_warning(provider, ctx["ticker"])

    inputs = apply_simple_ddm_overrides(defaults, request.GET)

    ddm_outputs = None
    ddm_error = None
    try:
        ddm_outputs = simple_ddm(inputs)
    except (ValueError, ZeroDivisionError) as e:
        ddm_error = str(e)

    upside_pct = _upside_pct(
        getattr(ddm_outputs, "fair_value", None), ctx.get("quote")
    )

    # Precompute D₁ for the template breakdown (cleaner than doing math in Django).
    d1 = inputs.current_dividend * (1.0 + inputs.growth_rate)

    ctx["ddm_inputs"] = inputs
    ctx["ddm_outputs"] = ddm_outputs
    ctx["ddm_error"] = ddm_error
    ctx["upside_pct"] = upside_pct
    ctx["d1"] = d1
    ctx["dividend_warning"] = dividend_warning
    ctx["model_label"] = "Simple Dividend Discount Model"
    ctx["model_category"] = "Intrinsic valuation"

    if request.GET.get("partial") == "results":
        return render(request, "valuation/_simple_ddm_results.html", ctx)

    return _render_tab(
        request,
        "valuation/simple_ddm.html",
        "valuation/_tab_simple_ddm.html",
        ctx,
    )


@require_GET
def two_stage_ddm_view(request: HttpRequest, ticker: str) -> HttpResponse:
    """Render the Two-Stage Dividend Discount Model page."""
    ctx, early = _base_ctx(request, ticker)
    if early is not None:
        return early
    ctx["active_tab"] = "models"

    provider = get_provider()

    defaults = derive_two_stage_ddm_defaults(
        provider, ctx["ticker"], ctx["profile"], ctx["quote"]
    )
    dividend_warning = _dividend_warning(provider, ctx["ticker"])

    inputs = apply_two_stage_ddm_overrides(defaults, request.GET)

    ddm_outputs = None
    ddm_error = None
    try:
        ddm_outputs = two_stage_ddm(inputs)
    except (ValueError, ZeroDivisionError) as e:
        ddm_error = str(e)

    upside_pct = _upside_pct(
        getattr(ddm_outputs, "fair_value", None), ctx.get("quote")
    )

    # Sum of PV(high-growth dividends) for the breakdown table. Derived
    # rather than re-summed: fair_value = sum_pv + pv_terminal_value.
    sum_pv_high_growth = None
    if ddm_outputs is not None:
        sum_pv_high_growth = (
            ddm_outputs.fair_value - ddm_outputs.pv_terminal_value
        )

    ctx["ddm_inputs"] = inputs
    ctx["ddm_outputs"] = ddm_outputs
    ctx["ddm_error"] = ddm_error
    ctx["upside_pct"] = upside_pct
    ctx["sum_pv_high_growth"] = sum_pv_high_growth
    ctx["dividend_warning"] = dividend_warning
    ctx["model_label"] = "Two-Stage Dividend Discount Model"
    ctx["model_category"] = "Intrinsic valuation"

    if request.GET.get("partial") == "results":
        return render(request, "valuation/_two_stage_ddm_results.html", ctx)

    return _render_tab(
        request,
        "valuation/two_stage_ddm.html",
        "valuation/_tab_two_stage_ddm.html",
        ctx,
    )
