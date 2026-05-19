"""View for the EV/EBITDA Multiple valuation page.

Lives in a sibling module so it can be authored in isolation; the main
``views.py`` will import :func:`ev_ebitda_view` and wire it into ``urls.py``.

Render modes mirror :func:`apps.valuation.views.dcf_pg_view`:
  * ``?partial=results``         -> just the results pane (form-driven swap)
  * htmx request without partial -> tab body fragment
  * neither                      -> full HTML page

Source: Corporate Finance Institute — "EV/EBITDA"
(https://corporatefinanceinstitute.com/resources/valuation/ev-ebitda/).
"""

from __future__ import annotations

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET

from apps.companies.views import _base_ctx, _render_tab
from apps.data.base import DataProviderError
from apps.data.registry import get_provider
from apps.valuation.defaults_ev_ebitda import (
    apply_ev_ebitda_overrides,
    derive_ev_ebitda_defaults,
)
from apps.valuation.engine.ev_ebitda import ev_ebitda_valuation


def _compute_current_ev_ebitda(profile, ebitda: float, net_debt: float) -> float | None:
    """Diagnostic ``(market_cap + net_debt) / ebitda`` — None if unavailable."""
    if profile is None or ebitda is None or ebitda <= 0:
        return None
    mc = getattr(profile, "market_cap", None)
    if mc is None:
        return None
    try:
        return (float(mc) + float(net_debt)) / float(ebitda)
    except (TypeError, ValueError, ZeroDivisionError):
        return None


@require_GET
def ev_ebitda_view(request: HttpRequest, ticker: str) -> HttpResponse:
    """Render the EV/EBITDA multiple valuation page for ``ticker``.

    Pulls defaults, layers query overrides, computes the firm's current
    EV/EBITDA from the profile (so the template can show "Current X / Target Y"),
    runs the engine, and renders a full / tab / results-only response per the
    same convention as the DCF view.
    """
    ctx, early = _base_ctx(request, ticker)
    if early is not None:
        return early
    ctx["active_tab"] = "models"

    provider = get_provider()
    inputs = derive_ev_ebitda_defaults(
        provider, ctx["ticker"], ctx["profile"], ctx["quote"]
    )
    inputs = apply_ev_ebitda_overrides(inputs, request.GET)

    # Compute the firm's current EV/EBITDA so the template can render a
    # "Current vs Target" comparison. Safe-fail to None.
    current_ev_ebitda = _compute_current_ev_ebitda(
        ctx.get("profile"), inputs.ebitda, inputs.net_debt
    )

    # Pull the ratios endpoint's ev_to_ebitda as a secondary reference (some
    # providers compute this differently — trailing vs. forward, etc.).
    ratios_ev_ebitda = None
    try:
        r = provider.get_ratios(ctx["ticker"])
        ratios_ev_ebitda = getattr(r, "ev_to_ebitda", None)
    except DataProviderError:
        pass

    ev_ebitda_outputs = None
    ev_ebitda_error = None
    try:
        ev_ebitda_outputs = ev_ebitda_valuation(inputs, current_multiple=current_ev_ebitda)
    except (ValueError, ZeroDivisionError) as e:
        ev_ebitda_error = str(e)

    upside_pct = None
    if ev_ebitda_outputs and ctx.get("quote") and ctx["quote"].price:
        upside_pct = (
            ev_ebitda_outputs.fair_value_per_share - ctx["quote"].price
        ) / ctx["quote"].price

    ctx["ev_ebitda_inputs"] = inputs
    ctx["ev_ebitda_outputs"] = ev_ebitda_outputs
    ctx["ev_ebitda_error"] = ev_ebitda_error
    ctx["upside_pct"] = upside_pct
    ctx["current_ev_ebitda"] = current_ev_ebitda
    ctx["ratios_ev_ebitda"] = ratios_ev_ebitda
    # Convenience flag for template colour coding (expansion vs compression).
    ctx["target_above_current"] = (
        current_ev_ebitda is not None
        and inputs.target_ev_ebitda > current_ev_ebitda
    )
    ctx["model_label"] = "EV / EBITDA Multiple"
    ctx["model_category"] = "Multiples valuation"

    if request.GET.get("partial") == "results":
        return render(request, "valuation/_ev_ebitda_results.html", ctx)

    return _render_tab(
        request,
        "valuation/ev_ebitda.html",
        "valuation/_tab_ev_ebitda.html",
        ctx,
    )
