"""View for the Reverse DCF page.

Lives in a sibling module so it can be authored in isolation; the main
``views.py`` will import :func:`reverse_dcf_view` and wire it into urls.py.

Render modes mirror :func:`apps.valuation.views.dcf_pg_view`:
  * ``?partial=results``         -> just the results pane (form-driven swap)
  * htmx request without partial -> tab body fragment
  * neither                      -> full HTML page

Source: Damodaran, "Implied Growth" notes; CFI Reverse DCF explainer.
"""

from __future__ import annotations

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET

from apps.companies.views import _base_ctx, _render_tab
from apps.data.registry import get_provider
from apps.valuation.defaults_reverse_dcf import (
    apply_reverse_dcf_overrides,
    derive_reverse_dcf_defaults,
)
from apps.valuation.engine.reverse_dcf import reverse_dcf


@require_GET
def reverse_dcf_view(request: HttpRequest, ticker: str) -> HttpResponse:
    """Render the Reverse DCF (implied growth) page for ``ticker``."""
    ctx, early = _base_ctx(request, ticker)
    if early is not None:
        return early
    ctx["active_tab"] = "models"

    provider = get_provider()
    inputs = derive_reverse_dcf_defaults(
        provider, ctx["ticker"], ctx["profile"], ctx["quote"]
    )

    reverse_error: str | None = None
    reverse_outputs = None

    if inputs is None:
        # Friendly error path: we can't invert without a current price.
        reverse_error = (
            "Live price unavailable for this ticker; reverse DCF needs a "
            "market price to solve against."
        )
    else:
        inputs = apply_reverse_dcf_overrides(inputs, request.GET)
        try:
            reverse_outputs = reverse_dcf(inputs)
        except (ValueError, ZeroDivisionError) as e:
            reverse_error = str(e)

    ctx["reverse_inputs"] = inputs
    ctx["reverse_outputs"] = reverse_outputs
    ctx["reverse_error"] = reverse_error
    ctx["current_price"] = inputs.current_price if inputs is not None else None
    ctx["model_label"] = "Reverse DCF — Implied Growth"
    ctx["model_category"] = "Multiples valuation"

    if request.GET.get("partial") == "results":
        return render(request, "valuation/_reverse_dcf_results.html", ctx)

    return _render_tab(
        request,
        "valuation/reverse_dcf.html",
        "valuation/_tab_reverse_dcf.html",
        ctx,
    )
