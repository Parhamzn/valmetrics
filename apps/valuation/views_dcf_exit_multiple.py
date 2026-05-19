"""View for the DCF — Exit Multiple page.

Lives in a sibling module so it can be authored in isolation; the main
``views.py`` will import :func:`dcf_exit_multiple_view` and wire it into
``urls.py``.

Render modes mirror :func:`apps.valuation.views.dcf_pg_view`:
  * ``?partial=results``         -> just the results pane (form-driven swap)
  * htmx request without partial -> tab body fragment
  * neither                      -> full HTML page

Source: CFI "Terminal Value"; Damodaran DCF notes.
"""

from __future__ import annotations

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET

from apps.companies.views import _base_ctx, _render_tab
from apps.data.registry import get_provider
from apps.valuation.defaults_dcf_exit_multiple import (
    apply_dcf_exit_multiple_overrides,
    derive_dcf_exit_multiple_defaults,
)
from apps.valuation.engine.dcf_exit_multiple import dcf_exit_multiple


@require_GET
def dcf_exit_multiple_view(request: HttpRequest, ticker: str) -> HttpResponse:
    """Render the DCF — Exit Multiple page for ``ticker``."""
    ctx, early = _base_ctx(request, ticker)
    if early is not None:
        return early
    ctx["active_tab"] = "models"

    provider = get_provider()
    inputs = derive_dcf_exit_multiple_defaults(
        provider, ctx["ticker"], ctx["profile"], ctx["quote"]
    )
    inputs = apply_dcf_exit_multiple_overrides(inputs, request.GET)

    dcf_outputs = None
    dcf_error = None
    try:
        dcf_outputs = dcf_exit_multiple(inputs)
    except (ValueError, ZeroDivisionError) as e:
        dcf_error = str(e)

    upside_pct = None
    if dcf_outputs and ctx.get("quote") and ctx["quote"].price:
        upside_pct = (
            dcf_outputs.fair_value_per_share - ctx["quote"].price
        ) / ctx["quote"].price

    ctx["dcf_inputs"] = inputs
    ctx["dcf_outputs"] = dcf_outputs
    ctx["dcf_error"] = dcf_error
    ctx["upside_pct"] = upside_pct
    ctx["model_label"] = "Discounted Cash Flow — Exit Multiple"
    ctx["model_category"] = "Multiples valuation"

    # Results-only partial (form-driven hx-get; URL not pushed).
    if request.GET.get("partial") == "results":
        return render(request, "valuation/_dcf_exit_multiple_results.html", ctx)

    return _render_tab(
        request,
        "valuation/dcf_exit_multiple.html",
        "valuation/_tab_dcf_exit_multiple.html",
        ctx,
    )
