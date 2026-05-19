"""View for the Peter Lynch fair-value page.

Lives in a sibling module so it can be authored in isolation; the main
``views.py`` will import :func:`peter_lynch_view` and wire it into urls.py.

Render modes mirror :func:`apps.valuation.views.dcf_pg_view`:
  * ``?partial=results``         -> just the results pane (form-driven swap)
  * htmx request without partial -> tab body fragment
  * neither                      -> full HTML page

Source: Lynch, *One Up on Wall Street*, ch. 10; Investopedia PEG ratio.
"""

from __future__ import annotations

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET

from apps.companies.views import _base_ctx, _render_tab
from apps.data.registry import get_provider
from apps.valuation.defaults_peter_lynch import (
    apply_peter_lynch_overrides,
    derive_peter_lynch_defaults,
)
from apps.valuation.engine.peter_lynch import peter_lynch_fair_value


@require_GET
def peter_lynch_view(request: HttpRequest, ticker: str) -> HttpResponse:
    """Render the Peter Lynch fair-value page for ``ticker``.

    Pulls defaults via :func:`derive_peter_lynch_defaults`, layers user
    overrides from the GET querydict, runs the engine, and renders a full
    page / tab fragment / results-only fragment per the same convention as
    the DCF view.
    """
    ctx, early = _base_ctx(request, ticker)
    if early is not None:
        return early
    ctx["active_tab"] = "models"

    provider = get_provider()
    inputs = derive_peter_lynch_defaults(
        provider, ctx["ticker"], ctx["profile"], ctx["quote"]
    )
    inputs = apply_peter_lynch_overrides(inputs, request.GET)

    # The engine never raises; warnings live on the outputs object.
    lynch_outputs = peter_lynch_fair_value(inputs)

    upside_pct = None
    if (
        lynch_outputs is not None
        and ctx.get("quote")
        and ctx["quote"].price
    ):
        upside_pct = (
            lynch_outputs.fair_value_per_share - ctx["quote"].price
        ) / ctx["quote"].price

    ctx["lynch_inputs"] = inputs
    ctx["lynch_outputs"] = lynch_outputs
    ctx["upside_pct"] = upside_pct
    ctx["model_label"] = "Peter Lynch Fair Value"
    ctx["model_category"] = "Multiples valuation"

    if request.GET.get("partial") == "results":
        return render(request, "valuation/_peter_lynch_results.html", ctx)

    return _render_tab(
        request,
        "valuation/peter_lynch.html",
        "valuation/_tab_peter_lynch.html",
        ctx,
    )
