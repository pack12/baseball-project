from django import template

register = template.Library()

DASH = "—"


@register.filter
def rate(value):
    """Baseball rate stat: .312, 1.045."""
    if value is None:
        return DASH
    text = f"{value:.3f}"
    return text[1:] if text.startswith("0") else text


@register.filter
def dec(value, places=1):
    return DASH if value is None else f"{value:.{places}f}"


@register.filter
def pct(value, places=1):
    """A 0-1 fraction as a percentage."""
    return DASH if value is None else f"{value * 100:.{places}f}%"


@register.filter
def signed(value, places=2):
    return DASH if value is None else f"{value:+.{places}f}"


@register.filter
def ordinal(value):
    if value is None:
        return DASH
    n = int(round(value))
    suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"
