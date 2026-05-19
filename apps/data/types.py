from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal


@dataclass(frozen=True)
class CompanyProfile:
    ticker: str
    name: str
    exchange: str
    currency: str
    sector: str
    industry: str
    country: str
    website: str
    description: str
    employees: int | None
    market_cap: float | None


@dataclass(frozen=True)
class Quote:
    ticker: str
    price: float
    currency: str
    change: float | None
    change_percent: float | None
    timestamp: datetime
    market_state: str | None


@dataclass(frozen=True)
class StatementLine:
    """Generic key/value row for a financial statement period.

    yfinance returns different field sets across companies, so we use a
    flexible dict rather than a fixed schema. Keys are normalized to
    snake_case strings.
    """

    period_end: date
    items: dict[str, float | None]


@dataclass(frozen=True)
class IncomeStatement:
    ticker: str
    currency: str
    period: Literal["annual", "quarterly"]
    lines: list[StatementLine]


@dataclass(frozen=True)
class BalanceSheet:
    ticker: str
    currency: str
    period: Literal["annual", "quarterly"]
    lines: list[StatementLine]


@dataclass(frozen=True)
class CashFlowStatement:
    ticker: str
    currency: str
    period: Literal["annual", "quarterly"]
    lines: list[StatementLine]


@dataclass(frozen=True)
class Ratios:
    ticker: str
    pe: float | None
    forward_pe: float | None
    peg: float | None
    price_to_book: float | None
    price_to_sales: float | None
    ev_to_ebitda: float | None
    dividend_yield: float | None
    return_on_equity: float | None
    return_on_assets: float | None
    debt_to_equity: float | None
    current_ratio: float | None
    gross_margin: float | None
    operating_margin: float | None
    profit_margin: float | None
    beta: float | None = None


@dataclass(frozen=True)
class PricePoint:
    date: date
    open: float
    high: float
    low: float
    close: float
    volume: float
    adj_close: float


@dataclass(frozen=True)
class PriceSeries:
    ticker: str
    currency: str
    points: list[PricePoint]


@dataclass(frozen=True)
class Dividend:
    date: date
    amount: float
