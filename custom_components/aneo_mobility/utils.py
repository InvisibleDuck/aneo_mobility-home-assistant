"""Div utils."""

from datetime import datetime, timedelta
import logging

from homeassistant.util import dt as dt_util

from .const import DATA_OPTIONS, DOMAIN

_LOGGER = logging.getLogger(__name__)


def get_option(hass, account_id, option, default=False):
    """Return option value, with settable default."""
    return hass.data[DOMAIN][account_id][DATA_OPTIONS].get(option, default)


def get_today():
    """Return today datetime (local, timezone-aware)."""
    return dt_util.now()


def get_tomorrow():
    """Return tomorrow datetime (local, timezone-aware)."""
    return dt_util.now() + timedelta(days=1)


def format_prices(prices, input_datetime):
    """Format prices into wanted format from Aneo format."""
    formatted_prices = []
    for hour in range(24):
        price_start = input_datetime.replace(
            hour=hour, minute=0, second=0, microsecond=0
        )
        price_stop = price_start + timedelta(hours=1)
        price = prices["prices"][hour]["price"]
        formatted_prices.append(
            {
                "price": price,
                "price_start": price_start,
                "price_stop": price_stop,
            }
        )
    return formatted_prices


def redact(value: str | None, keep: int = 4) -> str:
    """Redact identifiers before logging."""
    if not value:
        return "<none>"
    s = str(value)
    if len(s) <= keep:
        return "<redacted>"
    return f"<redacted:{s[-keep:]}>"
