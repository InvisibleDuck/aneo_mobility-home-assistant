"""The Aneo Mobility integration."""

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import device_registry as dr

from .api import AneoMobilityClient, InvalidRefreshToken
from .const import DOMAIN, ENTITY_TYPES
from .coordinator import (
    AneoMobilityChargerStateCoordinator,
    AneoMobilityPriceTrackerCoordinator,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the Aneo Mobility component."""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Aneo Mobility from a config entry."""

    # Create client from stored tokens (no password needed!)
    base_url = entry.data["base_url"]
    client = AneoMobilityClient(hass, base_url)
    client.load_tokens_from_entry(entry.data)

    # Try to refresh tokens to ensure they're valid
    try:
        tokens = await client.refresh()
        # Persist the new tokens (refresh token rotation)
        hass.config_entries.async_update_entry(
            entry, data={**entry.data, **client.tokens}
        )
    except InvalidRefreshToken as err:
        # Refresh token is invalid/expired -> trigger reauth
        raise ConfigEntryAuthFailed(
            "Refresh token expired, please re-authenticate"
        ) from err

    # Store client in hass.data for coordinators/platforms
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "client": client,
    }

    # Create coordinators
    coordinators = [
        AneoMobilityChargerStateCoordinator(hass, entry),
        AneoMobilityPriceTrackerCoordinator(hass, entry),
    ]

    for coordinator in coordinators:
        await coordinator.async_config_entry_first_refresh()

    # Store coordinators
    hass.data[DOMAIN][entry.entry_id]["coordinators"] = coordinators

    # Setup platforms
    await hass.config_entries.async_forward_entry_setups(entry, ENTITY_TYPES)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, ENTITY_TYPES)

    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
