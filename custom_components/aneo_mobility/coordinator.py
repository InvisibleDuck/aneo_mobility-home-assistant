"""Coordinator classes."""

from datetime import timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import InvalidAuth, InvalidRefreshToken
from .const import DEFAULT_INTERVAL_CHARGER_STATE, DEFAULT_INTERVAL_PRICE_DATA, DOMAIN
from .utils import redact

_LOGGER = logging.getLogger(__name__)


class AneoMobilityChargerStateCoordinator(DataUpdateCoordinator):
    """Coordinator to pull charger state."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialise coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name="Aneo Mobility Charger State",
            update_interval=timedelta(
                minutes=entry.options.get(
                    "interval_charger_state",
                    DEFAULT_INTERVAL_CHARGER_STATE,
                )
            ),
        )
        self.config_entry = entry

    async def _async_update_data(self):
        """Fetch charger state from API endpoint with automatic token refresh.

        Returns dict mapping charger_id -> {subscription, state} with socket status.
        """
        client = self.hass.data[DOMAIN][self.config_entry.entry_id]["client"]

        # Proactively refresh if access token is expired
        if not client.is_access_token_valid():
            _LOGGER.debug("Access token expired, refreshing proactively")
            try:
                await client.refresh()
                self.hass.config_entries.async_update_entry(
                    self.config_entry,
                    data={**self.config_entry.data, **client.tokens},
                )
            except InvalidRefreshToken as err:
                raise ConfigEntryAuthFailed(
                    "Refresh token expired, please re-authenticate"
                ) from err

        try:
            return await client.get_all_chargers_state()
        except InvalidAuth:
            # Access token expired (shouldn't happen after proactive check, but handle it)
            _LOGGER.debug("Access token expired during API call, attempting refresh")
            try:
                await client.refresh()
                self.hass.config_entries.async_update_entry(
                    self.config_entry,
                    data={**self.config_entry.data, **client.tokens},
                )
                # Retry the API call once
                return await client.get_all_chargers_state()
            except InvalidRefreshToken as err:
                raise ConfigEntryAuthFailed(
                    "Refresh token expired, please re-authenticate"
                ) from err
        except Exception as err:
            raise UpdateFailed(f"Error communicating with API: {err}") from err


class AneoMobilityPriceTrackerCoordinator(DataUpdateCoordinator):
    """Coordinator to pull price data."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialise coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name="Aneo Mobility Price Data",
            update_interval=timedelta(
                minutes=entry.options.get(
                    "interval_price_data",
                    DEFAULT_INTERVAL_PRICE_DATA,
                )
            ),
        )
        self.config_entry = entry

    async def _async_update_data(self):
        """Fetch price data from API endpoint with automatic token refresh."""
        client = self.hass.data[DOMAIN][self.config_entry.entry_id]["client"]

        # Proactively refresh if access token is expired
        if not client.is_access_token_valid():
            _LOGGER.debug("Access token expired, refreshing proactively")
            try:
                await client.refresh()
                self.hass.config_entries.async_update_entry(
                    self.config_entry,
                    data={**self.config_entry.data, **client.tokens},
                )
            except InvalidRefreshToken as err:
                raise ConfigEntryAuthFailed(
                    "Refresh token expired, please re-authenticate"
                ) from err

        # Get subscription_id from config entry (stored during setup)
        subscription_id = self.config_entry.data.get("subscription_id")

        if not subscription_id:
            # This shouldn't happen if config flow stored it, but handle gracefully
            raise UpdateFailed(
                "No subscription_id found in config entry. Please re-configure the integration."
            )

        _LOGGER.debug(
            "Fetching price data for subscription_id: %s", redact(subscription_id)
        )

        try:
            return await client.get_price_data(subscription_id)
        except InvalidAuth:
            _LOGGER.debug(
                "Access token expired during price API call, attempting refresh"
            )
            try:
                await client.refresh()
                self.hass.config_entries.async_update_entry(
                    self.config_entry,
                    data={**self.config_entry.data, **client.tokens},
                )
                return await client.get_price_data(subscription_id)
            except InvalidRefreshToken as err:
                raise ConfigEntryAuthFailed(
                    "Refresh token expired, please re-authenticate"
                ) from err
        except Exception as err:
            raise UpdateFailed(f"Error communicating with API: {err}") from err
