"""View for the Capital Asset Pricing Model (CAPM) page.

Lives in a sibling module so it can be authored in isolation; the main
``views.py`` will import :func:`capm_view` and wire it into ``urls.py``.

Render modes mirror :func:`apps.valuation.views.dcf_pg_view`:
  * ``?partial=results``         -> just the results pane (form-driven swap)
  * htmx request without partial -> tab body fragment
  * neither                      -> full HTML page

Source: Damodaran, *Investment Valuation*, ch. 7 (CAPM cost of equity).
"""

from __future__ import annotations

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET

from apps.companies.views import _base_ctx, _render_tab
from apps.data.registry import get_provider
from apps.valuation.defaults_capm import apply_capm_overrides, derive_capm_defaults
from apps.valuation.engine.capm import capm_cost_of_equity


@require_GET
def capm_view(request: HttpRequest, ticker: str) -> HttpResponse:
    """Render the CAPM cost-of-equity page for ``ticker``.

    Pulls defaults via :func:`derive_capm_defaults`, layers user overrides
    from the GET querydict, runs the engine, and renders a full page / tab
    fragment / results-only fragment per the same convention as the DCF view.
    """
    ctx, early = _base_ctx(request, ticker)
    if early is not None:
        return early
    ctx["active_tab"] = "models"

    provider = get_provider()
    inputs = derive_capm_defaults(
        provider, ctx["ticker"], ctx["profile"], ctx["quote"]
    )
    inputs = apply_capm_overrides(inputs, request.GET)

    capm_outputs = None
    capm_error = None
    try:
        capm_outputs = capm_cost_of_equity(inputs)
    except (ValueError, ZeroDivisionError) as e:
        capm_error = str(e)

    ctx["capm_inputs"] = inputs
    ctx["capm_outputs"] = capm_outputs
    ctx["capm_error"] = capm_error
    ctx["model_label"] = "Capital Asset Pricing Model"
    ctx["model_category"] = "Risk analysis"

    if request.GET.get("partial") == "results":
        return render(request, "valuation/_capm_results.html", ctx)

    return _render_tab(
        request,
        "valuation/capm.html",
        "valuation/_tab_capm.html",
        ctx,
    )
