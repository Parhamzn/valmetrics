from __future__ import annotations

import json

from django import template

from apps.companies.statement_layout import (
    BALANCE_LAYOUT,
    CASHFLOW_LAYOUT,
    INCOME_LAYOUT,
)

register = template.Library()


@register.simple_tag
def income_layout():
    return INCOME_LAYOUT


@register.simple_tag
def balance_layout():
    return BALANCE_LAYOUT


@register.simple_tag
def cashflow_layout():
    return CASHFLOW_LAYOUT


@register.simple_tag
def chart_data_for(statement, key, label=""):
    """Build a JSON payload for Chart.js for a single statement line.

    Returns a JSON string with shape:
        {"labels": ["2022-09-30", ...], "values": [123.0, ...], "label": "..."}

    Lines come oldest-first (Chart.js x-axis convention). Periods with a
    missing value are dropped entirely so the chart shows only real points.
    """
    if statement is None or not getattr(statement, "lines", None):
        payload = {"labels": [], "values": [], "label": label}
    else:
        # statement.lines is most-recent-first; reverse for chronological display
        pairs = []
        for line in reversed(statement.lines):
            v = (line.items or {}).get(key)
            if v is None:
                continue
            pairs.append((line.period_end.isoformat(), float(v)))
        payload = {
            "labels": [p[0] for p in pairs],
            "values": [p[1] for p in pairs],
            "label": label,
        }
    return json.dumps(payload)
