import time
import logging
import urllib.request
import json
from decimal import Decimal

logger = logging.getLogger(__name__)

_fx_cache = {
    'rates': {},
    'base': None,
    'timestamp': 0,
}

FX_CACHE_TTL = 600


def fetch_fx_rates(base='USD'):
    """Fetch live FX rates for given base currency.

    If a Django setting ``EXCHANGE_RATE_API_KEY`` is provided, we call the
    exchangerate-api.com service which supports nearly all global currencies
    (AED, INR, etc.).  The example request looks like
    ``https://v6.exchangerate-api.com/v6/{KEY}/latest/{base}``.

    On any failure the routine falls back to the previous providers in the
    following order:

    1. open.er-api.com (wide currency support but free-tier limited)
    2. frankfurter.app (original provider, still used as last resort)

    Results are cached for ``FX_CACHE_TTL`` seconds.  The function returns
    a tuple ``(rates_dict, timestamp)``.
    """
    now = time.time()
    if (
        _fx_cache['base'] == base
        and _fx_cache['rates']
        and (now - _fx_cache['timestamp']) < FX_CACHE_TTL
    ):
        return _fx_cache['rates'], _fx_cache['timestamp']

    # set up default rate map with base currency
    rates = {base: 1.0}

    # first try exchangerate-api.com if we have a key configured
    try:
        from django.conf import settings
    except ImportError:
        settings = None

    api_key = None
    if settings is not None:
        api_key = getattr(settings, 'EXCHANGE_RATE_API_KEY', None)

    if api_key:
        try:
            url = f'https://v6.exchangerate-api.com/v6/{api_key}/latest/{base}'
            req = urllib.request.Request(url, headers={'User-Agent': 'Splitgood/1.0'})
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode())

            # expected structure contains 'conversion_rates'
            if data.get('result') == 'success' and 'conversion_rates' in data:
                for code, rate in data['conversion_rates'].items():
                    rates[code] = float(rate)
                logger.info(
                    f"Fetched FX rates from exchangerate-api for base={base}, {len(rates)} currencies"
                )
                _fx_cache['rates'] = rates
                _fx_cache['base'] = base
                _fx_cache['timestamp'] = now
                return rates, now
            else:
                raise ValueError(f"unexpected response from exchangerate-api: {data}")
        except Exception as exc:
            logger.warning(f"ExchangeRate API failed ({exc}), falling back")
            # continue to next provider(s)

    # primary provider: open.er-api.com (previous behaviour)
    try:
        url = f'https://open.er-api.com/v6/latest/{base}'
        req = urllib.request.Request(url, headers={'User-Agent': 'Splitgood/1.0'})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
        # data should include 'rates'
        for code, rate in data.get('rates', {}).items():
            rates[code] = float(rate)
        logger.info(f"Fetched FX rates from er-api for base={base}, {len(rates)} currencies")
    except Exception as exc:
        logger.warning(f"Primary FX provider failed ({exc}), falling back")
        # fallback provider: frankfurter
        try:
            url = f'https://api.frankfurter.app/latest?from={base}'
            req = urllib.request.Request(url, headers={'User-Agent': 'Splitgood/1.0'})
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode())
            for code, rate in data.get('rates', {}).items():
                rates[code] = float(rate)
            logger.info(f"Fetched FX rates from frankfurter for base={base}, {len(rates)} currencies")
        except Exception as exc2:
            logger.error(f"Fallback FX rate fetch failed: {exc2}")
            if _fx_cache['rates'] and _fx_cache['base'] == base:
                return _fx_cache['rates'], _fx_cache['timestamp']
            # return minimal rate map with base only
            rates = {base: 1.0}

    # update cache and return
    _fx_cache['rates'] = rates
    _fx_cache['base'] = base
    _fx_cache['timestamp'] = now
    return rates, now


def convert_amount(amount, from_currency, to_currency, rates):
    if from_currency == to_currency:
        return float(amount)
    from_rate = rates.get(from_currency, 1.0)
    to_rate = rates.get(to_currency, 1.0)
    if from_rate == 0:
        return float(amount)
    return float(amount) / from_rate * to_rate


def compute_unified_balance(currency_map, target_currency, rates):
    total = 0.0
    for code, amount in currency_map.items():
        total += convert_amount(float(amount), code, target_currency, rates)
    return round(total, 2)


def detect_net_sign(currency_map, rates, reference_currency='USD'):
    if not currency_map:
        return 0
    total = 0.0
    for code, amount in currency_map.items():
        total += convert_amount(float(amount), code, reference_currency, rates)
    if total > 0.005:
        return 1
    elif total < -0.005:
        return -1
    return 0
