from __future__ import annotations

from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_GET, require_POST

from apps.data.base import DataProviderError, TickerNotFound
from apps.data.registry import get_provider
from apps.valuation.defaults import derive_dcf_defaults
from apps.valuation.engine.dcf import dcf_perpetual_growth

from .models import WatchlistItem


@require_GET
def list_view(request):
    """GET /watchlist/ — list all watched tickers with live quote + DCF fair value."""
    provider = get_provider()
    rows = []
    for item in WatchlistItem.objects.all():
        ticker = item.ticker
        profile = None
        quote = None
        fair_value = None
        upside_pct = None
        error = None

        try:
            profile = provider.get_profile(ticker)
        except TickerNotFound:
            # Skip rows whose ticker no longer resolves.
            continue
        except DataProviderError as e:
            rows.append({
                "item": item,
                "profile": None,
                "quote": None,
                "fair_value": None,
                "upside_pct": None,
                "error": str(e),
            })
            continue

        try:
            quote = provider.get_quote(ticker)
        except DataProviderError:
            quote = None
        except Exception:
            quote = None

        try:
            inputs = derive_dcf_defaults(provider, ticker, profile, quote)
            outputs = dcf_perpetual_growth(inputs)
            fair_value = outputs.fair_value_per_share
        except (ValueError, DataProviderError):
            fair_value = None
        except Exception:
            fair_value = None

        if fair_value is not None and quote is not None and getattr(quote, "price", None):
            try:
                upside_pct = (fair_value - quote.price) / quote.price
            except (TypeError, ZeroDivisionError):
                upside_pct = None

        rows.append({
            "item": item,
            "profile": profile,
            "quote": quote,
            "fair_value": fair_value,
            "upside_pct": upside_pct,
            "error": error,
        })

    return render(request, "watchlist/list.html", {"rows": rows})


@require_POST
def add(request):
    """POST /watchlist/add/?ticker=X — idempotent. Returns the toggle button partial."""
    ticker = (request.POST.get("ticker") or request.GET.get("ticker") or "").strip().upper()
    if not ticker:
        return HttpResponse("Missing ticker.", status=400)

    provider = get_provider()
    try:
        provider.get_profile(ticker)
    except TickerNotFound:
        return HttpResponse(
            f"<span class=\"error\">Ticker '{ticker}' not found.</span>",
            status=404,
        )
    except DataProviderError as e:
        return HttpResponse(
            f"<span class=\"error\">{e}</span>",
            status=502,
        )

    WatchlistItem.objects.get_or_create(ticker=ticker)
    return render(
        request,
        "watchlist/_toggle_button.html",
        {"ticker": ticker, "is_watched": True},
    )


@require_POST
def remove(request):
    """POST /watchlist/remove/?ticker=X — idempotent. Returns toggle button partial."""
    ticker = (request.POST.get("ticker") or request.GET.get("ticker") or "").strip().upper()
    WatchlistItem.objects.filter(ticker=ticker).delete()
    return render(
        request,
        "watchlist/_toggle_button.html",
        {"ticker": ticker, "is_watched": False},
    )


@require_POST
def update_notes(request, item_id: int):
    """POST /watchlist/items/<id>/notes/ with form field 'notes'. Saves and returns 204."""
    item = get_object_or_404(WatchlistItem, pk=item_id)
    item.notes = request.POST.get("notes", "")
    item.save()
    return HttpResponse(status=204)
