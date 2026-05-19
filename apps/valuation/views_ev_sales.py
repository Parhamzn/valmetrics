"""View for the EV/Sales Multiple valuation page.

Lives in a sibling module so it can be authored in isolation; the main
``views.py`` will import :func:`ev_sales_view` and wire it into ``urls.py``.

Render modes mirror :func:`apps.valuation.views.dcf_pg_view`.

Source: Damodaran, *Investment Valuation* ch. 20 (Revenue Multiples).
"""

from __future__ import annotations

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET

from apps.companies.views import _base_ctx, _render_tab
from apps.data.base import DataProviderError
from apps.data.registry import get_provider
from apps.valuation.defaults_ev_sales import (
    apply_ev_sales_overrides,
    derive_ev_sales_defaults,
)
from apps.valuation.engine.ev_sales import ev_sales_valuation


def _compute_current_ev_sales(profile, revenue: float, net_debt: float) -> float | None:
    """Diagnostic ``(market_cap + net_debt) / revenue`` — None if unavailable."""
    if profile is None or revenue is None or revenue <= 0:
        return None
    mc = getattr(profile, "market_cap", None)
    if mc is None:
        return None
    try:
        return (float(mc) + float(net_debt)) / float(revenue)
    except (TypeError, ValueError, ZeroDivisionError):
        return None


@require_GET
def ev_sales_view(request: HttpRequest, ticker: str) -> HttpResponse:
    """Render the EV/Sales multiple valuation page for ``ticker``.

    Unlike EV/EBITDA, this view works gracefully for unprofitable companies —
    revenue is almost always positive.
    """
    ctx, early = _base_ctx(request, ticker)
    if early is not None:
        return early
    ctx["active_tab"] = "models"

    provider = get_provider()
    inputs = derive_ev_sales_defaults(
        provider, ctx["ticker"], ctx["profile"], ctx["quote"]
    )
    inputs = apply_ev_sales_overrides(inputs, request.GET)

    current_ev_sales = _compute_current_ev_sales(
        ctx.get("profile"), inputs.revenue, inputs.net_debt
    )

    # Pull the equity-side P/S from the ratios endpoint as a secondary
    # diagnostic ("market cap / revenue" instead of "(mc + debt) / revenue").
    ratios_ps = None
    try:
        r = provider.get_ratios(ctx["ticker"])
        ratios_ps = getattr(r, "price_to_sales", None)
    except DataProviderError:
        pass

    ev_sales_outputs = None
    ev_sales_error = None
    try:
        ev_sales_outputs = ev_sales_valuation(inputs, current_multiple=current_ev_sales)
    except (ValueError, ZeroDivisionError) as e:
        ev_sales_error = str(e)

    upside_pct = None
    if ev_sales_outputs and ctx.get("quote") and ctx["quote"].price:
        upside_pct = (
            ev_sales_outputs.fair_value_per_share - ctx["quote"].price
        ) / ctx["quote"].price

    ctx["ev_sales_inputs"] = inputs
    ctx["ev_sales_outputs"] = ev_sales_outputs
    ctx["ev_sales_error"] = ev_sales_error
    ctx["upside_pct"] = upside_pct
    ctx["current_ev_sales"] = current_ev_sales
    ctx["ratios_price_to_sales"] = ratios_ps
    ctx["target_above_current"] = (
        current_ev_sales is not None
        and inputs.target_ev_sales > current_ev_sales
    )
    ctx["model_label"] = "EV / Sales Multiple"
    ctx["model_category"] = "Multiples valuation"

    if request.GET.get("partial") == "results":
        return render(request, "valuation/_ev_sales_results.html", ctx)

    return _render_tab(
        request,
        "valuation/ev_sales.html",
        "valuation/_tab_ev_sales.html",
        ctx,
    )
