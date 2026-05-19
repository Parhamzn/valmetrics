"""View for the Simple Excess Return Model.

Kept in a dedicated module per the coordination plan so DDM / EPV agents and
this one don't touch the same ``views.py``. The parent integration step will
wire the URL into ``apps/valuation/urls.py``.
"""

from __future__ import annotations

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET

from apps.companies.views import _base_ctx, _render_tab
from apps.data.registry import get_provider
from apps.valuation.defaults_excess_return import (
    apply_simple_excess_return_overrides,
    derive_simple_excess_return_defaults,
)
from apps.valuation.engine.excess_return import simple_excess_return


@require_GET
def simple_excess_return_view(request: HttpRequest, ticker: str) -> HttpResponse:
    """Render the Simple Excess Return Model for ``ticker``.

    Render modes (mirroring ``dcf_pg_view``):
      * ``?partial=results``         -> just the results pane (form-driven swap)
      * htmx request without partial -> tab body fragment
      * neither                      -> full HTML page
    """
    ctx, early = _base_ctx(request, ticker)
    if early is not None:
        return early
    ctx["active_tab"] = "models"

    provider = get_provider()
    inputs = derive_simple_excess_return_defaults(
        provider, ctx["ticker"], ctx["profile"], ctx["quote"]
    )
    inputs = apply_simple_excess_return_overrides(inputs, request.GET)

    excess_outputs = None
    excess_error = None
    try:
        excess_outputs = simple_excess_return(inputs)
    except (ValueError, ZeroDivisionError) as e:
        excess_error = str(e)

    upside_pct = None
    if excess_outputs and ctx.get("quote") and ctx["quote"].price:
        upside_pct = (
            excess_outputs.fair_value_per_share - ctx["quote"].price
        ) / ctx["quote"].price

    # Convenience scalar surfaced for the component breakdown in the template;
    # template-side arithmetic isn't expressive enough to derive it cleanly.
    pv_factor = None
    if inputs.cost_of_equity > inputs.growth_rate:
        pv_factor = (1.0 + inputs.growth_rate) / (
            inputs.cost_of_equity - inputs.growth_rate
        )

    ctx["excess_inputs"] = inputs
    ctx["excess_outputs"] = excess_outputs
    ctx["excess_error"] = excess_error
    ctx["upside_pct"] = upside_pct
    ctx["pv_factor"] = pv_factor
    ctx["model_label"] = "Simple Excess Return Model"
    ctx["model_category"] = "Intrinsic valuation"

    # Results-only partial (form-driven hx-get; URL not pushed).
    if request.GET.get("partial") == "results":
        return render(
            request, "valuation/_simple_excess_return_results.html", ctx
        )

    return _render_tab(
        request,
        "valuation/simple_excess_return.html",
        "valuation/_tab_simple_excess_return.html",
        ctx,
    )
