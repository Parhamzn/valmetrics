"""View for the Margin Analysis operational page.

Lives in a sibling module so it can be authored without colliding with
concurrent edits to the main ``views.py``. Integration into ``urls.py`` and
``MODEL_CATEGORIES`` happens at the end by the parent process.

Render modes mirror :func:`apps.valuation.views.dcf_pg_view`:
  * ``?partial=results``         -> results-only fragment (form-driven swap)
  * htmx request without partial -> tab body fragment
  * neither                      -> full HTML page

Source: Corporate Finance Institute, "Profit Margin".
"""

from __future__ import annotations

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET

from apps.companies.views import _base_ctx, _render_tab
from apps.data.registry import get_provider
from apps.valuation.defaults_margin_analysis import (
    derive_margin_analysis_defaults,
)
from apps.valuation.engine.margin_analysis import margin_analysis


@require_GET
def margin_analysis_view(request: HttpRequest, ticker: str) -> HttpResponse:
    """Render the Margin Analysis page for ``ticker``.

    No user inputs: the page is a historical-trend view. We still expose the
    standard three render modes so the URL behaves like every other model tab.
    """
    ctx, early = _base_ctx(request, ticker)
    if early is not None:
        return early
    ctx["active_tab"] = "models"

    provider = get_provider()
    inputs = derive_margin_analysis_defaults(
        provider, ctx["ticker"], ctx["profile"], ctx["quote"]
    )

    margin_outputs = None
    margin_error = None
    try:
        margin_outputs = margin_analysis(inputs)
    except (ValueError, ZeroDivisionError) as e:
        margin_error = str(e)

    # Pre-bake chart-ready bar heights so the template doesn't have to do
    # math. Bars are sized as percentages of the max margin in the dataset
    # (capped at 100%); the template multiplies by the CSS max height.
    chart_rows = []
    chart_max = None
    if margin_outputs and margin_outputs.points:
        all_vals = []
        for p in margin_outputs.points:
            for v in (p.gross_margin, p.operating_margin, p.profit_margin):
                if v is not None:
                    all_vals.append(v)
        chart_max = max(all_vals) if all_vals else None
        if chart_max is not None and chart_max <= 0:
            chart_max = None

        for p in margin_outputs.points:
            def _h(v):
                if v is None or chart_max in (None, 0):
                    return 0
                # Clamp negative margins to 0 so bars don't render below axis.
                pct = max(0.0, v) / chart_max
                return round(pct * 100)
            chart_rows.append({
                "period_end": p.period_end,
                "gross_margin": p.gross_margin,
                "operating_margin": p.operating_margin,
                "profit_margin": p.profit_margin,
                "gross_h": _h(p.gross_margin),
                "op_h": _h(p.operating_margin),
                "net_h": _h(p.profit_margin),
            })

    ctx["margin_inputs"] = inputs
    ctx["margin_outputs"] = margin_outputs
    ctx["margin_error"] = margin_error
    ctx["margin_chart_rows"] = chart_rows
    ctx["margin_chart_max"] = chart_max
    ctx["model_label"] = "Margin Analysis"
    ctx["model_category"] = "Risk analysis"

    if request.GET.get("partial") == "results":
        return render(request, "valuation/_margin_analysis_results.html", ctx)

    return _render_tab(
        request,
        "valuation/margin_analysis.html",
        "valuation/_tab_margin_analysis.html",
        ctx,
    )
