from __future__ import annotations

from typing import Literal, Protocol, runtime_checkable

from apps.data.types import (
    BalanceSheet,
    CashFlowStatement,
    CompanyProfile,
    Dividend,
    IncomeStatement,
    PriceSeries,
    Quote,
    Ratios,
)


class DataProviderError(Exception):
    """Base exception for data-provider failures."""


class TickerNotFound(DataProviderError):
    """Raised when the provider cannot resolve a ticker symbol."""


class RateLimited(DataProviderError):
    """Raised when the upstream provider rate-limits us."""


class UpstreamError(DataProviderError):
    """Raised on generic upstream failures (network, parse, etc.)."""


@runtime_checkable
class DataProvider(Protocol):
    """Abstract interface every concrete data provider must satisfy."""

    def get_profile(self, ticker: str) -> CompanyProfile: ...

    def get_quote(self, ticker: str) -> Quote: ...

    def get_income_statement(
        self,
        ticker: str,
        *,
        period: Literal["annual", "quarterly"] = "annual",
    ) -> IncomeStatement: ...

    def get_balance_sheet(
        self,
        ticker: str,
        *,
        period: Literal["annual", "quarterly"] = "annual",
    ) -> BalanceSheet: ...

    def get_cash_flow(
        self,
        ticker: str,
        *,
        period: Literal["annual", "quarterly"] = "annual",
    ) -> CashFlowStatement: ...

    def get_ratios(self, ticker: str) -> Ratios: ...

    def get_price_history(
        self,
        ticker: str,
        *,
        period: str = "5y",
        interval: str = "1d",
    ) -> PriceSeries: ...

    def get_dividends(self, ticker: str) -> list[Dividend]: ...

    def search(self, query: str, *, limit: int = 10) -> list[CompanyProfile]: ...
