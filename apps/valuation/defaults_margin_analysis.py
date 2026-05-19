"""Default-input derivation for the Margin Analysis operational page.

Margin Analysis is purely historical: there's nothing the user can override,
so this module exposes only :func:`derive_margin_analysis_defaults`. It fetches
the annual income statement and stuffs the raw provider lines straight into
the engine inputs. The engine handles missing / malformed rows.

Source: Corporate Finance Institute, "Profit Margin"
(https://corporatefinanceinstitute.com/resources/accounting/profit-margin/).
"""

from __future__ import annotations

from apps.data.base import DataProviderError
from apps.valuation.engine.types_margin_analysis import MarginAnalysisInputs


def derive_margin_analysis_defaults(
    provider, ticker, profile=None, quote=None
) -> MarginAnalysisInputs:
    """Build :class:`MarginAnalysisInputs` from the provider.

    Only the annual income statement is needed; the engine derives gross /
    operating / net margins from the per-period line items. ``profile`` and
    ``quote`` are accepted to keep the call site signature uniform with the
    other ``derive_*_defaults`` helpers, but they're unused here.
    """
    income = None
    try:
        income = provider.get_income_statement(ticker, period="annual")
    except DataProviderError:
        income = None

    lines = []
    if income is not None:
        lines = list(getattr(income, "lines", None) or [])

    return MarginAnalysisInputs(ticker=ticker, annual_periods=lines)
