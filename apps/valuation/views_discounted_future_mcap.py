"""View for the Discounted Future Market Cap page.

Lives in a sibling module so it can be authored in isolation; the main
``views.py`` imports :func:`dfmc_view` and wires it into ``urls.py``.

Render modes mirror :func:`apps.valuation.views.dcf_pg_view`.
"""

from __future__ import annotations

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET

from apps.companies.views import _base_ctx, _render_tab
from apps.data.registry import get_provider
from apps.valuation.defaults_discounted_future_mcap import (
    apply_dfmc_overrides,
    derive_dfmc_defaults,
)
from apps.valuation.engine.discounted_future_mcap import discounted_future_mcap


@require_GET
def dfmc_view(request: HttpRequest, ticker: str) -> HttpResponse:
    """Render the Discounted Future Market Cap page for ``ticker``."""
    ctx, early = _base_ctx(request, ticker)
    if early is not None:
        return early
    ctx["active_tab"] = "models"

    provider = get_provider()
    inputs = derive_dfmc_defaults(
        provider, ctx["ticker"], ctx["profile"], ctx["quote"]
    )
    inputs = apply_dfmc_overrides(inputs, request.GET)

    dfmc_outputs = None
    dfmc_error = None
    try:
        dfmc_outputs = discounted_future_mcap(inputs)
    except (ValueError, ZeroDivisionError) as e:
        dfmc_error = str(e)

    upside_pct = None
    if dfmc_outputs and ctx.get("quote") and ctx["quote"].price:
        upside_pct = (
            dfmc_outputs.fair_value_per_share - ctx["quote"].price
        ) / ctx["quote"].price

    ctx["dfmc_inputs"] = inputs
    ctx["dfmc_outputs"] = dfmc_outputs
    ctx["dfmc_error"] = dfmc_error
    ctx["upside_pct"] = upside_pct
    # Surface the loss-making case for the template (the engine itself stays
    # silent; see ``discounted_future_mcap`` docstring).
    ctx["is_loss_making"] = inputs.base_net_income <= 0
    ctx["model_label"] = "Discounted Future Market Cap"
    ctx["model_category"] = "Multiples valuation"

    if request.GET.get("partial") == "results":
        return render(
            request, "valuation/_discounted_future_mcap_results.html", ctx
        )

    return _render_tab(
        request,
        "valuation/discounted_future_mcap.html",
        "valuation/_tab_discounted_future_mcap.html",
        ctx,
    )
