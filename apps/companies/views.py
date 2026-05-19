from __future__ import annotations

from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_GET

from apps.data.base import DataProviderError, TickerNotFound
from apps.data.registry import get_provider

POPULAR_TICKERS = ["AAPL", "NVDA", "MSFT", "GOOGL", "AMZN", "META", "TSLA", "BRK-B"]


def _render_tab(request, full_template, partial_template, ctx):
    """Render the partial if this is an htmx request, else the full page."""
    template = partial_template if request.headers.get("HX-Request") else full_template
    return render(request, template, ctx)


def _base_ctx(request, ticker):
    """Resolve ticker + profile + quote + period for any tab view.

    Returns either a tuple (ctx, None) with the shared context dict, or
    (None, response) when an early HTTP response (Http404/error page) should
    short-circuit the view.
    """
    ticker = ticker.upper()
    provider = get_provider()

    try:
        profile = provider.get_profile(ticker)
    except TickerNotFound:
        raise Http404(f"Ticker '{ticker}' not found.")
    except DataProviderError as e:
        return None, render(
            request,
            "companies/error.html",
            {"ticker": ticker, "message": str(e)},
            status=502,
        )

    quote = None
    try:
        quote = provider.get_quote(ticker)
    except DataProviderError:
        pass

    period = request.GET.get("period", "annual")
    if period not in ("annual", "quarterly"):
        period = "annual"

    ctx = {
        "ticker": ticker,
        "profile": profile,
        "quote": quote,
        "period": period,
    }
    # Watchlist state (best-effort; tolerate missing table during fresh installs)
    from apps.watchlist.services import is_watched as _is_watched
    ctx["is_watched"] = _is_watched(ticker)
    return ctx, None


@require_GET
def home(request: HttpRequest) -> HttpResponse:
    return render(request, "companies/home.html", {"popular": POPULAR_TICKERS})


@require_GET
def search(request: HttpRequest) -> HttpResponse:
    q = (request.GET.get("q") or "").strip()
    is_htmx = bool(request.headers.get("HX-Request"))

    if not q:
        if is_htmx:
            return render(request, "companies/_search_suggest.html", {"results": [], "query": ""})
        return redirect("/")

    try:
        results = get_provider().search(q, limit=10)
    except DataProviderError:
        results = []

    ctx = {"query": q, "results": results}

    if is_htmx:
        return render(request, "companies/_search_suggest.html", ctx)

    upper_q = q.upper()
    for r in results:
        if r.ticker.upper() == upper_q:
            return redirect("companies:overview", ticker=r.ticker)

    if not results:
        return render(request, "companies/search_results.html", ctx, status=404)
    return render(request, "companies/search_results.html", ctx)


@require_GET
def company_root(request: HttpRequest, ticker: str) -> HttpResponse:
    return redirect("companies:overview", ticker=ticker.upper())


@require_GET
def overview(request: HttpRequest, ticker: str) -> HttpResponse:
    ctx, early = _base_ctx(request, ticker)
    if early is not None:
        return early
    ctx["active_tab"] = "overview"
    return _render_tab(
        request,
        "companies/overview.html",
        "companies/_tab_overview.html",
        ctx,
    )


@require_GET
def income_statement(request: HttpRequest, ticker: str) -> HttpResponse:
    ctx, early = _base_ctx(request, ticker)
    if early is not None:
        return early
    ctx["active_tab"] = "income"

    provider = get_provider()
    statement = None
    statement_error = None
    try:
        statement = provider.get_income_statement(ctx["ticker"], period=ctx["period"])
    except DataProviderError as e:
        statement_error = str(e)

    ctx["statement"] = statement
    ctx["statement_error"] = statement_error
    return _render_tab(
        request,
        "companies/income.html",
        "companies/_tab_income.html",
        ctx,
    )


@require_GET
def balance_sheet(request: HttpRequest, ticker: str) -> HttpResponse:
    ctx, early = _base_ctx(request, ticker)
    if early is not None:
        return early
    ctx["active_tab"] = "balance"

    provider = get_provider()
    statement = None
    statement_error = None
    try:
        statement = provider.get_balance_sheet(ctx["ticker"], period=ctx["period"])
    except DataProviderError as e:
        statement_error = str(e)

    ctx["statement"] = statement
    ctx["statement_error"] = statement_error
    return _render_tab(
        request,
        "companies/balance.html",
        "companies/_tab_balance.html",
        ctx,
    )


@require_GET
def cash_flow(request: HttpRequest, ticker: str) -> HttpResponse:
    ctx, early = _base_ctx(request, ticker)
    if early is not None:
        return early
    ctx["active_tab"] = "cashflow"

    provider = get_provider()
    statement = None
    statement_error = None
    try:
        statement = provider.get_cash_flow(ctx["ticker"], period=ctx["period"])
    except DataProviderError as e:
        statement_error = str(e)

    ctx["statement"] = statement
    ctx["statement_error"] = statement_error
    return _render_tab(
        request,
        "companies/cashflow.html",
        "companies/_tab_cashflow.html",
        ctx,
    )


@require_GET
def ratios(request: HttpRequest, ticker: str) -> HttpResponse:
    ctx, early = _base_ctx(request, ticker)
    if early is not None:
        return early
    ctx["active_tab"] = "ratios"

    provider = get_provider()
    ratios_data = None
    ratios_error = None
    try:
        ratios_data = provider.get_ratios(ctx["ticker"])
    except DataProviderError as e:
        ratios_error = str(e)

    pays_dividend = None
    try:
        divs = provider.get_dividends(ctx["ticker"])
        if not divs:
            pays_dividend = False
        else:
            from datetime import date, timedelta
            cutoff = date.today() - timedelta(days=730)
            pays_dividend = any(d.date >= cutoff for d in divs)
    except DataProviderError:
        pass

    is_loss_making = None
    if ratios_data is not None and ratios_data.profit_margin is not None:
        is_loss_making = ratios_data.profit_margin < 0

    ctx["ratios"] = ratios_data
    ctx["ratios_error"] = ratios_error
    ctx["pays_dividend"] = pays_dividend
    ctx["is_loss_making"] = is_loss_making
    return _render_tab(
        request,
        "companies/ratios.html",
        "companies/_tab_ratios.html",
        ctx,
    )
