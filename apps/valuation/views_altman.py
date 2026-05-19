"""View for the Altman Z-Score page.

Lives in a sibling module so it can be authored in isolation; the main
``views.py`` will import :func:`altman_view` and wire it into ``urls.py``.

Render modes mirror :func:`apps.valuation.views.dcf_pg_view`:
  * ``?partial=results``         -> just the results pane (form-driven swap)
  * htmx request without partial -> tab body fragment
  * neither                      -> full HTML page

Source: Altman (1968), Journal of Finance.
"""

from __future__ import annotations

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET

from apps.companies.views import _base_ctx, _render_tab
from apps.data.registry import get_provider
from apps.valuation.defaults_altman import derive_altman_defaults
from apps.valuation.engine.altman import altman_z_score


@require_GET
def altman_view(request: HttpRequest, ticker: str) -> HttpResponse:
    """Render the Altman Z-Score page for ``ticker``.

    No assumptions form: Altman Z is a fixed weighted formula over reported
    statements + market cap.
    """
    ctx, early = _base_ctx(request, ticker)
    if early is not None:
        return early
    ctx["active_tab"] = "models"

    provider = get_provider()
    inputs = derive_altman_defaults(
        provider, ctx["ticker"], ctx["profile"], ctx["quote"]
    )

    altman_outputs = None
    altman_error = None
    try:
        altman_outputs = altman_z_score(inputs)
    except (ValueError, ZeroDivisionError) as e:
        altman_error = str(e)

    ctx["altman_inputs"] = inputs
    ctx["altman_outputs"] = altman_outputs
    ctx["altman_error"] = altman_error
    ctx["model_label"] = "Altman Z-Score"
    ctx["model_category"] = "Risk analysis"

    if request.GET.get("partial") == "results":
        return render(request, "valuation/_altman_results.html", ctx)

    return _render_tab(
        request,
        "valuation/altman.html",
        "valuation/_tab_altman.html",
        ctx,
    )
