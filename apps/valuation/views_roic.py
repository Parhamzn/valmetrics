"""View for the ROIC (Return on Invested Capital) operational page.

Render modes mirror :func:`apps.valuation.views.dcf_pg_view`:
  * ``?partial=results``         -> results-only fragment (form-driven swap)
  * htmx request without partial -> tab body fragment
  * neither                      -> full HTML page

Source: Damodaran, returnmeasures.pdf (NYU Stern); Investopedia ROIC.
"""

from __future__ import annotations

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET

from apps.companies.views import _base_ctx, _render_tab
from apps.data.registry import get_provider
from apps.valuation.defaults_roic import apply_roic_overrides, derive_roic_defaults
from apps.valuation.engine.roic import compute_roic


@require_GET
def roic_view(request: HttpRequest, ticker: str) -> HttpResponse:
    """Render the ROIC page for ``ticker``."""
    ctx, early = _base_ctx(request, ticker)
    if early is not None:
        return early
    ctx["active_tab"] = "models"

    provider = get_provider()
    inputs = derive_roic_defaults(
        provider, ctx["ticker"], ctx["profile"], ctx["quote"]
    )
    inputs = apply_roic_overrides(inputs, request.GET)

    roic_outputs = None
    roic_error = None
    try:
        roic_outputs = compute_roic(inputs)
    except (ValueError, ZeroDivisionError) as e:
        roic_error = str(e)

    # Pre-bake chart-ready bar heights so the template doesn't have to do
    # math. The chart's vertical scale spans 0 to max(roic, wacc) so the
    # WACC reference line is always visible.
    chart_rows = []
    chart_max = None
    wacc_h_pct = None
    if roic_outputs and roic_outputs.points:
        roic_vals = [p.roic for p in roic_outputs.points if p.roic is not None]
        if roic_vals:
            chart_max = max(max(roic_vals), inputs.wacc_estimate)
        else:
            chart_max = inputs.wacc_estimate
        if chart_max <= 0:
            chart_max = None

        if chart_max:
            wacc_h_pct = round(max(0.0, inputs.wacc_estimate) / chart_max * 100)

        for p in roic_outputs.points:
            if p.roic is None or chart_max in (None, 0):
                h = 0
                above = None
            else:
                h = round(max(0.0, p.roic) / chart_max * 100)
                above = p.roic > inputs.wacc_estimate
            chart_rows.append({
                "period_end": p.period_end,
                "nopat": p.nopat,
                "invested_capital": p.invested_capital,
                "roic": p.roic,
                "h": h,
                "above": above,
            })

    # Convenience scalar: spread between latest ROIC and WACC (in percent
    # points), for the "creates 10 pts of value" headline copy.
    spread_pts = None
    if roic_outputs and roic_outputs.latest.roic is not None:
        spread_pts = (roic_outputs.latest.roic - inputs.wacc_estimate) * 100.0

    ctx["roic_inputs"] = inputs
    ctx["roic_outputs"] = roic_outputs
    ctx["roic_error"] = roic_error
    ctx["roic_chart_rows"] = chart_rows
    ctx["roic_chart_max"] = chart_max
    ctx["roic_wacc_h_pct"] = wacc_h_pct
    ctx["roic_spread_pts"] = spread_pts
    ctx["model_label"] = "Return on Invested Capital"
    ctx["model_category"] = "Risk analysis"

    if request.GET.get("partial") == "results":
        return render(request, "valuation/_roic_results.html", ctx)

    return _render_tab(
        request,
        "valuation/roic.html",
        "valuation/_tab_roic.html",
        ctx,
    )
