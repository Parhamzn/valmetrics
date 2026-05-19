"""View for the Piotroski F-Score page.

Lives in a sibling module so it can be authored in isolation; the main
``views.py`` will import :func:`piotroski_view` and wire it into ``urls.py``.

Render modes mirror :func:`apps.valuation.views.dcf_pg_view`:
  * ``?partial=results``         -> just the results pane (form-driven swap)
  * htmx request without partial -> tab body fragment
  * neither                      -> full HTML page

Source: Piotroski (2000), Journal of Accounting Research.
"""

from __future__ import annotations

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET

from apps.companies.views import _base_ctx, _render_tab
from apps.data.registry import get_provider
from apps.valuation.defaults_piotroski import derive_piotroski_defaults
from apps.valuation.engine.piotroski import piotroski_f_score


@require_GET
def piotroski_view(request: HttpRequest, ticker: str) -> HttpResponse:
    """Render the Piotroski F-Score page for ``ticker``.

    No assumptions form: the F-Score is a fixed checklist over reported
    statements, so the view simply derives inputs, computes the score, and
    renders the result.
    """
    ctx, early = _base_ctx(request, ticker)
    if early is not None:
        return early
    ctx["active_tab"] = "models"

    provider = get_provider()
    inputs = derive_piotroski_defaults(
        provider, ctx["ticker"], ctx["profile"], ctx["quote"]
    )

    piotroski_outputs = None
    piotroski_error = None
    try:
        piotroski_outputs = piotroski_f_score(inputs)
    except (ValueError, ZeroDivisionError) as e:
        piotroski_error = str(e)

    ctx["piotroski_inputs"] = inputs
    ctx["piotroski_outputs"] = piotroski_outputs
    ctx["piotroski_error"] = piotroski_error
    ctx["model_label"] = "Piotroski F-Score"
    ctx["model_category"] = "Risk analysis"

    # Results-only partial (kept for symmetry with the other model views even
    # though there's no form: lets future tweaks ship without re-plumbing).
    if request.GET.get("partial") == "results":
        return render(request, "valuation/_piotroski_results.html", ctx)

    return _render_tab(
        request,
        "valuation/piotroski.html",
        "valuation/_tab_piotroski.html",
        ctx,
    )
