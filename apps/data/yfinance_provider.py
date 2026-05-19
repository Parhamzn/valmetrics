from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

import requests

from apps.data.base import (
    DataProviderError,
    RateLimited,
    TickerNotFound,
    UpstreamError,
)
from apps.data.cache import cached
from apps.data.types import (
    BalanceSheet,
    CashFlowStatement,
    CompanyProfile,
    Dividend,
    IncomeStatement,
    PricePoint,
    PriceSeries,
    Quote,
    Ratios,
    StatementLine,
)

logger = logging.getLogger(__name__)

try:  # Import yfinance lazily-tolerantly: module should load even if it fails.
    import yfinance as yf  # type: ignore
except Exception as _yf_import_exc:  # pragma: no cover
    yf = None  # type: ignore[assignment]
    logger.warning(
        "yfinance could not be imported (%s); YFinanceProvider will fail at call time.",
        _yf_import_exc,
    )


_SNAKE_RE_1 = re.compile(r"[^0-9a-zA-Z]+")
_SNAKE_RE_2 = re.compile(r"([a-z0-9])([A-Z])")


def _normalize_key(s: str) -> str:
    """Convert an arbitrary statement label to snake_case.

    Examples:
        "Total Revenue" -> "total_revenue"
        "EBITDA" -> "ebitda"
        "NetIncomeFromContinuingOps" -> "net_income_from_continuing_ops"
    """
    if s is None:
        return ""
    # Insert underscore between lower/digit followed by Upper (camelCase).
    s = _SNAKE_RE_2.sub(r"\1_\2", str(s))
    # Replace any run of non-alphanumeric chars with a single underscore.
    s = _SNAKE_RE_1.sub("_", s)
    return s.strip("_").lower()


def _to_float_or_none(value: Any) -> float | None:
    """Coerce a value (possibly NaN/None/numpy) to float|None."""
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    # NaN check without importing numpy/math at top.
    if f != f:  # noqa: PLR0124
        return None
    return f


def _to_int_or_none(value: Any) -> int | None:
    f = _to_float_or_none(value)
    if f is None:
        return None
    try:
        return int(f)
    except (TypeError, ValueError):
        return None


def _require_yf() -> None:
    if yf is None:
        raise UpstreamError("yfinance is not installed or failed to import")


def _safe_info(t: Any) -> dict[str, Any]:
    """Pull a `.info`-ish dict from a yf.Ticker, tolerating known flakiness."""
    info: dict[str, Any] = {}
    # yfinance 0.2.x: `.info` can intermittently raise / return None. Try
    # `.get_info()` (newer) first if present, then `.info`, then `.fast_info`
    # keys as a last resort. Wrap each in its own try/except — we want to
    # collect whatever fields we can.
    for accessor in ("get_info", "info"):
        try:
            attr = getattr(t, accessor, None)
            value = attr() if callable(attr) else attr
            if isinstance(value, dict) and value:
                info.update(value)
                break
        except Exception as exc:
            logger.debug("yfinance %s failed: %s", accessor, exc)
            continue
    return info


class YFinanceProvider:
    """Concrete DataProvider implementation backed by yfinance."""

    # ----- profile -----------------------------------------------------------

    @cached(category="profile", ttl=timedelta(days=7))
    def get_profile(self, ticker: str) -> CompanyProfile:
        _require_yf()
        t = yf.Ticker(ticker)
        info = _safe_info(t)
        if not info or not info.get("symbol") and not info.get("shortName") and not info.get("longName"):
            # Probe fast_info for a price as a sanity check before declaring not found.
            try:
                fi = getattr(t, "fast_info", None)
                if fi is None or _to_float_or_none(getattr(fi, "last_price", None)) is None:
                    raise TickerNotFound(f"Unknown ticker: {ticker}")
            except TickerNotFound:
                raise
            except Exception as exc:
                raise TickerNotFound(f"Unknown ticker: {ticker}") from exc

        return CompanyProfile(
            ticker=str(info.get("symbol") or ticker).upper(),
            name=str(info.get("longName") or info.get("shortName") or ""),
            exchange=str(info.get("exchange") or info.get("fullExchangeName") or ""),
            currency=str(info.get("currency") or info.get("financialCurrency") or ""),
            sector=str(info.get("sector") or ""),
            industry=str(info.get("industry") or ""),
            country=str(info.get("country") or ""),
            website=str(info.get("website") or ""),
            description=str(info.get("longBusinessSummary") or ""),
            employees=_to_int_or_none(info.get("fullTimeEmployees")),
            market_cap=_to_float_or_none(info.get("marketCap")),
        )

    # ----- quote -------------------------------------------------------------

    @cached(category="quote", ttl=timedelta(seconds=60))
    def get_quote(self, ticker: str) -> Quote:
        _require_yf()
        t = yf.Ticker(ticker)
        price: float | None = None
        currency = ""
        market_state: str | None = None
        prev_close: float | None = None

        # Primary path: .fast_info
        try:
            fi = t.fast_info  # property; can raise on bad tickers
            price = _to_float_or_none(getattr(fi, "last_price", None))
            currency = str(getattr(fi, "currency", "") or "")
            market_state = getattr(fi, "market_state", None)
            if market_state is not None:
                market_state = str(market_state)
            prev_close = _to_float_or_none(getattr(fi, "previous_close", None))
        except Exception as exc:
            logger.debug("fast_info failed for %s: %s", ticker, exc)

        # Fallback: last row of .history(period="1d")
        if price is None:
            try:
                hist = t.history(period="1d")
                if hist is not None and not hist.empty:
                    last = hist.iloc[-1]
                    price = _to_float_or_none(last.get("Close"))
                    if len(hist) >= 2:
                        prev_close = _to_float_or_none(hist.iloc[-2].get("Close"))
                    if not currency:
                        info = _safe_info(t)
                        currency = str(info.get("currency") or "")
            except Exception as exc:
                raise UpstreamError(f"Failed to fetch quote for {ticker}: {exc}") from exc

        if price is None:
            raise TickerNotFound(f"No quote data for {ticker}")

        change: float | None = None
        change_percent: float | None = None
        if prev_close is not None and prev_close != 0:
            change = price - prev_close
            change_percent = (change / prev_close) * 100.0

        return Quote(
            ticker=ticker.upper(),
            price=price,
            currency=currency,
            change=change,
            change_percent=change_percent,
            timestamp=datetime.now(timezone.utc),
            market_state=market_state,
        )

    # ----- statements --------------------------------------------------------

    def _build_lines(self, df: Any) -> list[StatementLine]:
        """Convert a yfinance financials DataFrame into StatementLines.

        yfinance returns each statement as a DataFrame where columns are
        period-end dates and rows are line-item labels.
        """
        lines: list[StatementLine] = []
        if df is None:
            return lines
        try:
            if df.empty:
                return lines
        except Exception:
            return lines

        for col in df.columns:
            # Column label is the period-end (Timestamp or date).
            try:
                period_end = col.date() if hasattr(col, "date") else col
            except Exception:
                period_end = col
            items: dict[str, float | None] = {}
            series = df[col]
            for label, value in series.items():
                key = _normalize_key(str(label))
                if not key:
                    continue
                items[key] = _to_float_or_none(value)
            lines.append(StatementLine(period_end=period_end, items=items))

        # Most-recent first.
        def _sort_key(line: StatementLine) -> Any:
            pe = line.period_end
            return pe if pe is not None else datetime.min.date()

        lines.sort(key=_sort_key, reverse=True)
        return lines

    def _statement_currency(self, ticker_obj: Any) -> str:
        info = _safe_info(ticker_obj)
        return str(info.get("financialCurrency") or info.get("currency") or "")

    @cached(category="statements", ttl=timedelta(days=1))
    def get_income_statement(
        self,
        ticker: str,
        *,
        period: Literal["annual", "quarterly"] = "annual",
    ) -> IncomeStatement:
        _require_yf()
        t = yf.Ticker(ticker)
        try:
            df = t.quarterly_financials if period == "quarterly" else t.financials
        except Exception as exc:
            raise UpstreamError(f"Failed to fetch income statement for {ticker}: {exc}") from exc
        lines = self._build_lines(df)
        if not lines:
            raise TickerNotFound(f"No income statement data for {ticker}")
        return IncomeStatement(
            ticker=ticker.upper(),
            currency=self._statement_currency(t),
            period=period,
            lines=lines,
        )

    @cached(category="statements", ttl=timedelta(days=1))
    def get_balance_sheet(
        self,
        ticker: str,
        *,
        period: Literal["annual", "quarterly"] = "annual",
    ) -> BalanceSheet:
        _require_yf()
        t = yf.Ticker(ticker)
        try:
            df = t.quarterly_balance_sheet if period == "quarterly" else t.balance_sheet
        except Exception as exc:
            raise UpstreamError(f"Failed to fetch balance sheet for {ticker}: {exc}") from exc
        lines = self._build_lines(df)
        if not lines:
            raise TickerNotFound(f"No balance sheet data for {ticker}")
        return BalanceSheet(
            ticker=ticker.upper(),
            currency=self._statement_currency(t),
            period=period,
            lines=lines,
        )

    @cached(category="statements", ttl=timedelta(days=1))
    def get_cash_flow(
        self,
        ticker: str,
        *,
        period: Literal["annual", "quarterly"] = "annual",
    ) -> CashFlowStatement:
        _require_yf()
        t = yf.Ticker(ticker)
        try:
            df = t.quarterly_cashflow if period == "quarterly" else t.cashflow
        except Exception as exc:
            raise UpstreamError(f"Failed to fetch cash flow for {ticker}: {exc}") from exc
        lines = self._build_lines(df)
        if not lines:
            raise TickerNotFound(f"No cash flow data for {ticker}")
        return CashFlowStatement(
            ticker=ticker.upper(),
            currency=self._statement_currency(t),
            period=period,
            lines=lines,
        )

    # ----- ratios ------------------------------------------------------------

    @cached(category="ratios", ttl=timedelta(minutes=15))
    def get_ratios(self, ticker: str) -> Ratios:
        _require_yf()
        t = yf.Ticker(ticker)
        info = _safe_info(t)
        if not info:
            raise TickerNotFound(f"No ratios data for {ticker}")
        return Ratios(
            ticker=ticker.upper(),
            pe=_to_float_or_none(info.get("trailingPE")),
            forward_pe=_to_float_or_none(info.get("forwardPE")),
            peg=_to_float_or_none(info.get("pegRatio")),
            price_to_book=_to_float_or_none(info.get("priceToBook")),
            price_to_sales=_to_float_or_none(info.get("priceToSalesTrailing12Months")),
            ev_to_ebitda=_to_float_or_none(info.get("enterpriseToEbitda")),
            dividend_yield=self._compute_dividend_yield(ticker, info),
            return_on_equity=_to_float_or_none(info.get("returnOnEquity")),
            return_on_assets=_to_float_or_none(info.get("returnOnAssets")),
            debt_to_equity=_to_float_or_none(info.get("debtToEquity")),
            current_ratio=_to_float_or_none(info.get("currentRatio")),
            gross_margin=_to_float_or_none(info.get("grossMargins")),
            operating_margin=_to_float_or_none(info.get("operatingMargins")),
            profit_margin=_to_float_or_none(info.get("profitMargins")),
            beta=_to_float_or_none(info.get("beta")),
        )

    def _compute_dividend_yield(self, ticker: str, info: dict) -> float | None:
        """Compute trailing-12-month dividend yield as a decimal.

        yfinance's `dividendYield` flips between decimal (0.004) and percent (0.40)
        for the same field over time. We sidestep that by computing it ourselves
        from the last 12 months of actual dividend payments divided by the
        current price. Falls back to yfinance's value (with a magnitude-based
        normalization) when we can't compute ours.
        """
        try:
            quote = self.get_quote(ticker)
            dividends = self.get_dividends(ticker)
            if quote and quote.price and dividends:
                from datetime import date as _date
                cutoff = _date.today() - timedelta(days=365)
                ttm = sum(d.amount for d in dividends if d.date >= cutoff)
                if ttm > 0:
                    return ttm / quote.price
        except Exception as exc:
            logger.debug("Could not compute TTM yield for %s: %s", ticker, exc)

        raw = _to_float_or_none(info.get("dividendYield"))
        if raw is None:
            return None
        return raw / 100.0 if raw > 1.0 else raw

    # ----- prices / dividends -----------------------------------------------

    @cached(category="price_history", ttl=timedelta(hours=1))
    def get_price_history(
        self,
        ticker: str,
        *,
        period: str = "5y",
        interval: str = "1d",
    ) -> PriceSeries:
        _require_yf()
        t = yf.Ticker(ticker)
        try:
            df = t.history(period=period, interval=interval, auto_adjust=False)
        except Exception as exc:
            raise UpstreamError(f"Failed to fetch price history for {ticker}: {exc}") from exc

        points: list[PricePoint] = []
        if df is None or df.empty:
            raise TickerNotFound(f"No price history for {ticker}")

        # yfinance returns columns: Open, High, Low, Close, Adj Close, Volume.
        # When auto_adjust=False the "Adj Close" column is present; fall back
        # to "Close" if missing.
        for idx, row in df.iterrows():
            try:
                d = idx.date() if hasattr(idx, "date") else idx
            except Exception:
                d = idx
            close = _to_float_or_none(row.get("Close"))
            adj = _to_float_or_none(row.get("Adj Close"))
            if adj is None:
                adj = close if close is not None else 0.0
            points.append(
                PricePoint(
                    date=d,
                    open=_to_float_or_none(row.get("Open")) or 0.0,
                    high=_to_float_or_none(row.get("High")) or 0.0,
                    low=_to_float_or_none(row.get("Low")) or 0.0,
                    close=close or 0.0,
                    volume=_to_float_or_none(row.get("Volume")) or 0.0,
                    adj_close=adj,
                )
            )

        # Pull currency from fast_info or info.
        currency = ""
        try:
            fi = t.fast_info
            currency = str(getattr(fi, "currency", "") or "")
        except Exception:
            pass
        if not currency:
            info = _safe_info(t)
            currency = str(info.get("currency") or "")

        return PriceSeries(ticker=ticker.upper(), currency=currency, points=points)

    @cached(category="dividends", ttl=timedelta(days=1))
    def get_dividends(self, ticker: str) -> list[Dividend]:
        _require_yf()
        t = yf.Ticker(ticker)
        try:
            series = t.dividends
        except Exception as exc:
            raise UpstreamError(f"Failed to fetch dividends for {ticker}: {exc}") from exc

        out: list[Dividend] = []
        if series is None:
            return out
        try:
            if series.empty:
                return out
        except Exception:
            return out

        for idx, value in series.items():
            try:
                d = idx.date() if hasattr(idx, "date") else idx
            except Exception:
                d = idx
            amount = _to_float_or_none(value)
            if amount is None:
                continue
            out.append(Dividend(date=d, amount=amount))
        return out

    # ----- search ------------------------------------------------------------

    @cached(category="search", ttl=timedelta(days=1))
    def search(self, query: str, *, limit: int = 10) -> list[CompanyProfile]:
        query = (query or "").strip()
        if not query:
            return []
        try:
            resp = requests.get(
                "https://query1.finance.yahoo.com/v1/finance/search",
                params={"q": query, "quotesCount": max(limit * 3, 15), "newsCount": 0},
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=4,
            )
            resp.raise_for_status()
            quotes = resp.json().get("quotes", [])
        except Exception as exc:
            logger.debug("Yahoo search failed for %r: %s", query, exc)
            return []

        allowed_types = {"EQUITY", "ETF", "MUTUALFUND", "INDEX"}
        results: list[CompanyProfile] = []
        for q in quotes:
            qtype = (q.get("quoteType") or "").upper()
            if qtype not in allowed_types:
                continue
            symbol = q.get("symbol")
            if not symbol:
                continue
            results.append(
                CompanyProfile(
                    ticker=str(symbol).upper(),
                    name=str(q.get("longname") or q.get("shortname") or ""),
                    exchange=str(q.get("exchDisp") or q.get("exchange") or ""),
                    currency="",
                    sector=str(q.get("sectorDisp") or q.get("sector") or ""),
                    industry=str(q.get("industryDisp") or q.get("industry") or ""),
                    country="",
                    website="",
                    description=str(q.get("typeDisp") or qtype),
                    employees=None,
                    market_cap=None,
                )
            )
            if len(results) >= limit:
                break
        return results


__all__ = [
    "YFinanceProvider",
    "DataProviderError",
    "TickerNotFound",
    "RateLimited",
    "UpstreamError",
]
