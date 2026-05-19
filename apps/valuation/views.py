"""Views for the valuation app.

Two endpoints:

* :func:`models_index` — a catalog page listing every valuation model we plan
  to support, grouped by category. Most models are currently placeholders
  (``available=False``); only the DCF perpetual-growth model is wired up.

* :func:`dcf_pg_view` — the live perpetual-growth DCF page. It composes
  defaults from the data provider, layers user overrides from the querydict,
  runs the engine, and renders either a full page, a tab body, or just the
  results pane depending on the htmx context.
"""

from __future__ import annotations

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET

from apps.companies.views import _base_ctx, _render_tab
from apps.data.registry import get_provider
from apps.valuation.defaults import apply_query_overrides, derive_dcf_defaults
from apps.valuation.engine.dcf import (
    dcf_perpetual_growth as dcf_perpetual_growth_engine,
)
from apps.valuation.views_ddm import simple_ddm_view, two_stage_ddm_view
from apps.valuation.views_epv import epv_view
from apps.valuation.views_excess_return import simple_excess_return_view
from apps.valuation.views_dcf_exit_multiple import dcf_exit_multiple_view
from apps.valuation.views_discounted_future_mcap import dfmc_view
from apps.valuation.views_peter_lynch import peter_lynch_view
from apps.valuation.views_reverse_dcf import reverse_dcf_view
from apps.valuation.views_ev_ebitda import ev_ebitda_view
from apps.valuation.views_ev_sales import ev_sales_view
from apps.valuation.views_capm import capm_view
from apps.valuation.views_wacc import wacc_view
from apps.valuation.views_piotroski import piotroski_view
from apps.valuation.views_altman import altman_view
from apps.valuation.views_margin_analysis import margin_analysis_view
from apps.valuation.views_roic import roic_view

__all__ = [
    "models_index",
    "dcf_pg_view",
    "simple_ddm_view",
    "two_stage_ddm_view",
    "epv_view",
    "simple_excess_return_view",
    "dcf_exit_multiple_view",
    "dfmc_view",
    "peter_lynch_view",
    "reverse_dcf_view",
    "ev_ebitda_view",
    "ev_sales_view",
    "capm_view",
    "wacc_view",
    "piotroski_view",
    "altman_view",
    "margin_analysis_view",
    "roic_view",
]


# ---------------------------------------------------------------------------
# Model catalog
# ---------------------------------------------------------------------------
#
# Surfaced by ``models_index`` and reused by the DCF page for breadcrumb /
# nav rendering. ``url_name`` is None for models that are not yet built so
# templates can render them as disabled cards.
#

MODEL_CATEGORIES = [
    {
        "name": "Intrinsic valuation",
        "slug": "intrinsic-valuation",
        "models": [
            {
                "label": "Discounted Cash Flow — Perpetual Growth",
                "slug": "dcf-perpetual-growth",
                "url_name": "valuation:dcf_perpetual_growth",
                "available": True,
            },
            {
                "label": "Simple Dividend Discount Model",
                "slug": "simple-dividend-discount-model",
                "url_name": "valuation:simple_ddm",
                "available": True,
            },
            {
                "label": "Two-Stage Dividend Discount Model",
                "slug": "two-stage-dividend-discount-model",
                "url_name": "valuation:two_stage_ddm",
                "available": True,
            },
            {
                "label": "Earnings Power Value",
                "slug": "earnings-power-value",
                "url_name": "valuation:epv",
                "available": True,
            },
            {
                "label": "Simple Excess Return Model",
                "slug": "simple-excess-return",
                "url_name": "valuation:simple_excess_return",
                "available": True,
            },
        ],
    },
    {
        "name": "Multiples valuation",
        "slug": "multiples-valuation",
        "models": [
            {
                "label": "DCF — Exit Multiple",
                "slug": "dcf-exit-multiple",
                "url_name": "valuation:dcf_exit_multiple",
                "available": True,
            },
            {
                "label": "Discounted Future Market Cap",
                "slug": "discounted-future-market-cap",
                "url_name": "valuation:discounted_future_mcap",
                "available": True,
            },
            {
                "label": "Peter Lynch Fair Value",
                "slug": "peter-lynch-fair-value",
                "url_name": "valuation:peter_lynch",
                "available": True,
            },
            {
                "label": "Reverse DCF — Implied Growth",
                "slug": "reverse-dcf",
                "url_name": "valuation:reverse_dcf",
                "available": True,
            },
            {
                "label": "EV / EBITDA Multiple",
                "slug": "ev-ebitda",
                "url_name": "valuation:ev_ebitda",
                "available": True,
            },
            {
                "label": "EV / Sales Multiple",
                "slug": "ev-sales",
                "url_name": "valuation:ev_sales",
                "available": True,
            },
        ],
    },
    {
        "name": "Risk analysis",
        "slug": "risk-analysis",
        "models": [
            {
                "label": "Weighted Average Cost of Capital (WACC)",
                "slug": "weighted-average-cost-of-capital-wacc",
                "url_name": "valuation:wacc",
                "available": True,
            },
            {
                "label": "Capital Asset Pricing Model (CAPM)",
                "slug": "capital-asset-pricing-model-capm",
                "url_name": "valuation:capm",
                "available": True,
            },
            {
                "label": "Piotroski F-Score",
                "slug": "piotroski-f-score",
                "url_name": "valuation:piotroski",
                "available": True,
            },
            {
                "label": "Altman Z-Score",
                "slug": "altman-z-score",
                "url_name": "valuation:altman",
                "available": True,
            },
            {
                "label": "Margin Analysis",
                "slug": "margin-analysis",
                "url_name": "valuation:margin_analysis",
                "available": True,
            },
            {
                "label": "Return on Invested Capital (ROIC)",
                "slug": "return-on-invested-capital-roic",
                "url_name": "valuation:roic",
                "available": True,
            },
        ],
    },
]


# ---------------------------------------------------------------------------
# Views
# ---------------------------------------------------------------------------


@require_GET
def models_index(request: HttpRequest, ticker: str) -> HttpResponse:
    """List all available valuation models for ``ticker``."""
    ctx, early = _base_ctx(request, ticker)
    if early is not None:
        return early
    ctx["active_tab"] = "models"
    ctx["categories"] = MODEL_CATEGORIES
    return _render_tab(
        request,
        "valuation/models_index.html",
        "valuation/_tab_models_index.html",
        ctx,
    )


@require_GET
def dcf_pg_view(request: HttpRequest, ticker: str) -> HttpResponse:
    """Render the perpetual-growth DCF for ``ticker``.

    Render modes:
      * ``?partial=results``         -> just the results pane (form-driven swap)
      * htmx request without partial -> tab body fragment
      * neither                      -> full HTML page
    """
    ctx, early = _base_ctx(request, ticker)
    if early is not None:
        return early
    ctx["active_tab"] = "models"

    provider = get_provider()
    inputs = derive_dcf_defaults(
        provider, ctx["ticker"], ctx["profile"], ctx["quote"]
    )
    inputs = apply_query_overrides(inputs, request.GET)

    dcf_outputs = None
    dcf_error = None
    try:
        dcf_outputs = dcf_perpetual_growth_engine(inputs)
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
    ctx["model_label"] = "Discounted Cash Flow — Perpetual Growth"
    ctx["model_category"] = "Intrinsic valuation"

    # Results-only partial (form-driven hx-get; URL not pushed).
    if request.GET.get("partial") == "results":
        return render(request, "valuation/_dcf_results.html", ctx)

    return _render_tab(
        request,
        "valuation/dcf_perpetual_growth.html",
        "valuation/_tab_dcf.html",
        ctx,
    )
