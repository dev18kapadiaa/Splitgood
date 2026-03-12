from django import template
from core.currencies import (
    format_multi_currency_balance,
    format_multi_currency_additive,
    get_currency_symbol,
    format_currency,
)

register = template.Library()


@register.filter
def multi_currency(currency_map):
    if not currency_map or not isinstance(currency_map, dict):
        return '$0.00'
    return format_multi_currency_balance(currency_map)


@register.filter
def multi_currency_add(currency_map):
    if not currency_map or not isinstance(currency_map, dict):
        return '$0.00'
    return format_multi_currency_additive(currency_map)


@register.filter
def currency_symbol(code):
    return get_currency_symbol(code)


@register.filter
def format_amount(amount, currency_code='USD'):
    from decimal import Decimal
    if amount is None:
        amount = Decimal('0')
    return format_currency(amount, currency_code)


@register.filter
def is_all_zero(currency_map):
    if not currency_map or not isinstance(currency_map, dict):
        return True
    return all(v == 0 for v in currency_map.values())


@register.filter
def is_net_positive(currency_map):
    """Check if the multi-currency balance is net positive by converting to INR."""
    if not currency_map or not isinstance(currency_map, dict):
        return False
    from core.fx_service import fetch_fx_rates, detect_net_sign
    rates, _ = fetch_fx_rates('USD')
    sign = detect_net_sign(currency_map, rates, 'INR')
    return sign > 0


@register.filter
def is_net_negative(currency_map):
    """Check if the multi-currency balance is net negative by converting to INR."""
    if not currency_map or not isinstance(currency_map, dict):
        return False
    from core.fx_service import fetch_fx_rates, detect_net_sign
    rates, _ = fetch_fx_rates('USD')
    sign = detect_net_sign(currency_map, rates, 'INR')
    return sign < 0
