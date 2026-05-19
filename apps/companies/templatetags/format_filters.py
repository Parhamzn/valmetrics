from __future__ import annotations

from django import template

register = template.Library()


@register.filter
def humanize(value):
    """4374482124800 -> '4.37T'. None -> '—'."""
    if value is None:
        return "—"
    try:
        n = float(value)
    except (TypeError, ValueError):
        return value
    abs_n = abs(n)
    if abs_n >= 1e12:
        return f"{n / 1e12:.2f}T"
    if abs_n >= 1e9:
        return f"{n / 1e9:.2f}B"
    if abs_n >= 1e6:
        return f"{n / 1e6:.2f}M"
    if abs_n >= 1e3:
        return f"{n / 1e3:.2f}K"
    return f"{n:.2f}"


@register.filter
def percent(value, places=2):
    if value is None:
        return "—"
    try:
        return f"{float(value) * 100:.{places}f}%"
    except (TypeError, ValueError):
        return value


@register.filter
def or_dash(value):
    if value is None or value == "":
        return "—"
    return value


@register.filter
def signed_color(value):
    """Returns a Tailwind color class based on sign."""
    if value is None:
        return "text-gray-500"
    try:
        v = float(value)
    except (TypeError, ValueError):
        return "text-gray-500"
    if v > 0:
        return "text-green-600"
    if v < 0:
        return "text-red-600"
    return "text-gray-500"


@register.filter
def money(value):
    """Format a currency amount as $XX.XXT/B/M/K. None -> '—'. Handles negatives."""
    if value is None:
        return "—"
    try:
        n = float(value)
    except (TypeError, ValueError):
        return value
    if n != n:  # NaN
        return "—"
    sign = "-" if n < 0 else ""
    abs_n = abs(n)
    if abs_n >= 1e12:
        return f"{sign}${abs_n / 1e12:.2f}T"
    if abs_n >= 1e9:
        return f"{sign}${abs_n / 1e9:.2f}B"
    if abs_n >= 1e6:
        return f"{sign}${abs_n / 1e6:.2f}M"
    if abs_n >= 1e3:
        return f"{sign}${abs_n / 1e3:.2f}K"
    return f"{sign}${abs_n:.2f}"


@register.filter
def get_item(d, key):
    """Look up a key in a dict-like object. Returns None on missing/invalid."""
    if d is None:
        return None
    try:
        return d.get(key)
    except AttributeError:
        return None
