from __future__ import annotations

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
