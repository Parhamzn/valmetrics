"""View for the Weighted-Average Cost of Capital (WACC) page.

Lives in a sibling module so it can be authored in isolation; the main
``views.py`` will import :func:`wacc_view` and wire it into ``urls.py``.

Render modes mirror :func:`apps.valuation.views.dcf_pg_view`:
  * ``?partial=results``         -> just the results pane (form-driven swap)
  * htmx request without partial -> tab body fragment
  * neither                      -> full HTML page

Source: Damodaran cost-of-capital lecture notes.
"""

from __future__ import annotations

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET

from apps.companies.views import _base_ctx, _render_tab
from apps.data.registry import get_provider
from apps.valuation.defaults_wacc import apply_wacc_overrides, derive_wacc_defaults
from apps.valuation.engine.wacc import wacc as wacc_engine


@require_GET
def wacc_view(request: HttpRequest, ticker: str) -> HttpResponse:
    """Render the WACC page for ``ticker``."""
    ctx, early = _base_ctx(request, ticker)
    if early is not None:
        return early
    ctx["active_tab"] = "models"

    provider = get_provider()
    inputs = derive_wacc_defaults(
        provider, ctx["ticker"], ctx["profile"], ctx["quote"]
    )
    inputs = apply_wacc_overrides(inputs, request.GET)

    wacc_outputs = None
    wacc_error = None
    try:
        wacc_outputs = wacc_engine(inputs)
    except (ValueError, ZeroDivisionError) as e:
        wacc_error = str(e)

    # Pre-compute display-only intermediates so templates can render the
    # breakdown without doing arithmetic.
    after_tax_kd = inputs.cost_of_debt * (1.0 - inputs.tax_rate)
    ctx["after_tax_kd"] = after_tax_kd
    ctx["equity_weight_pct"] = (
        wacc_outputs.equity_weight * 100.0 if wacc_outputs else None
    )
    ctx["debt_weight_pct"] = (
        wacc_outputs.debt_weight * 100.0 if wacc_outputs else None
    )

    ctx["wacc_inputs"] = inputs
    ctx["wacc_outputs"] = wacc_outputs
    ctx["wacc_error"] = wacc_error
    ctx["model_label"] = "Weighted Average Cost of Capital"
    ctx["model_category"] = "Risk analysis"

    if request.GET.get("partial") == "results":
        return render(request, "valuation/_wacc_results.html", ctx)

    return _render_tab(
        request,
        "valuation/wacc.html",
        "valuation/_tab_wacc.html",
        ctx,
    )
