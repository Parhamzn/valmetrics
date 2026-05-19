"""View for the Earnings Power Value (EPV) page.

Lives in a sibling module so it can be authored in isolation; the main
``views.py`` will import :func:`epv_view` and wire it into ``urls.py``.

Render modes mirror :func:`apps.valuation.views.dcf_pg_view`:
  * ``?partial=results``         -> just the results pane (form-driven swap)
  * htmx request without partial -> tab body fragment
  * neither                      -> full HTML page

Source: Greenwald et al., *Value Investing*, ch. 6 (EPV methodology).
"""

from __future__ import annotations

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET

from apps.companies.views import _base_ctx, _render_tab
from apps.data.registry import get_provider
from apps.valuation.defaults_epv import apply_epv_overrides, derive_epv_defaults
from apps.valuation.engine.epv import earnings_power_value


@require_GET
def epv_view(request: HttpRequest, ticker: str) -> HttpResponse:
    """Render the Earnings Power Value page for ``ticker``.

    Pulls defaults via :func:`derive_epv_defaults`, layers user overrides from
    the GET querydict, runs the engine, and renders a full page / tab fragment
    / results-only fragment per the same convention as the DCF view.
    """
    ctx, early = _base_ctx(request, ticker)
    if early is not None:
        return early
    ctx["active_tab"] = "models"

    provider = get_provider()
    inputs = derive_epv_defaults(
        provider, ctx["ticker"], ctx["profile"], ctx["quote"]
    )
    inputs = apply_epv_overrides(inputs, request.GET)

    epv_outputs = None
    epv_error = None
    try:
        epv_outputs = earnings_power_value(inputs)
    except (ValueError, ZeroDivisionError) as e:
        epv_error = str(e)

    upside_pct = None
    if epv_outputs and ctx.get("quote") and ctx["quote"].price:
        upside_pct = (
            epv_outputs.epv_per_share - ctx["quote"].price
        ) / ctx["quote"].price

    ctx["epv_inputs"] = inputs
    ctx["epv_outputs"] = epv_outputs
    ctx["epv_error"] = epv_error
    ctx["upside_pct"] = upside_pct
    ctx["model_label"] = "Earnings Power Value"
    ctx["model_category"] = "Intrinsic valuation"

    # Results-only partial (form-driven hx-get; URL not pushed).
    if request.GET.get("partial") == "results":
        return render(request, "valuation/_epv_results.html", ctx)

    return _render_tab(
        request,
        "valuation/epv.html",
        "valuation/_tab_epv.html",
        ctx,
    )
