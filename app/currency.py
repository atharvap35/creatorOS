"""Currency-aware money formatting shared by routes and templates."""

from contextvars import ContextVar
from typing import Optional

CURRENCY_SYMBOLS = {
    "USD": "$",
    "EUR": "€",
    "GBP": "£",
    "INR": "₹",
    "AUD": "A$",
    "CAD": "C$",
    "SGD": "S$",
    "AED": "AED ",
    "JPY": "¥",
    "BRL": "R$",
    "ZAR": "R",
}

DEFAULT_CURRENCY = "USD"

current_currency: ContextVar[str] = ContextVar("current_currency", default=DEFAULT_CURRENCY)


def symbol(currency: Optional[str] = None) -> str:
    code = (currency or current_currency.get() or DEFAULT_CURRENCY).upper()
    return CURRENCY_SYMBOLS.get(code, f"{code} ")


def _group(digits: str, indian: bool) -> str:
    if indian:
        head, tail = digits[:-3], digits[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        grouped = ",".join(parts + [tail])
    else:
        grouped = f"{int(digits):,}"
    return grouped


def money(value, currency: Optional[str] = None, decimals: int = 2, suffix: bool = False) -> str:
    """Format a number with the active (or given) currency symbol.

    Example: money(1500, "INR") -> "₹1,500.00"
    """
    try:
        amount = float(value or 0)
    except (TypeError, ValueError):
        amount = 0.0

    code = (currency or current_currency.get() or DEFAULT_CURRENCY).upper()
    indian = code == "INR"

    rounded = round(abs(amount), decimals)
    whole, _, fraction = f"{rounded:.{decimals}f}".partition(".")
    formatted = _group(whole, indian)
    sign = "-" if amount < 0 else ""
    tail = f".{fraction}" if decimals else ""
    prefix = "" if suffix else symbol(currency)

    return f"{sign}{prefix}{formatted}{tail}"


def money_compact(value, currency: Optional[str] = None) -> str:
    """Short form for chart axes: $12.4k, ₹1.2L."""
    try:
        amount = float(value or 0)
    except (TypeError, ValueError):
        amount = 0.0

    sign = "-" if amount < 0 else ""
    amount = abs(amount)
    for threshold, suffix in ((1_000_000, "M"), (1_000, "K")):
        if amount >= threshold:
            return f"{sign}{symbol(currency)}{amount / threshold:.1f}{suffix}"
    return f"{sign}{symbol(currency)}{amount:.0f}"
