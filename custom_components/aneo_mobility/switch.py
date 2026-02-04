"""Switch platform for Aneo Mobility."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.exceptions import HomeAssistantError

from .base import AneoMobilityEntity
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Aneo Mobility switch platform."""
    coordinators = hass.data[DOMAIN][config_entry.entry_id]["coordinators"]
    charger_state_coordinator = coordinators[0]

    entities = []
    if charger_state_coordinator.data:
        for charger_id in charger_state_coordinator.data:
            entities.append(
                AneoMobilityChargingSwitch(
                    charger_state_coordinator, config_entry, charger_id
                )
            )
            entities.append(
                AneoMobilityCableLockSwitch(
                    charger_state_coordinator, config_entry, charger_id
                )
            )

    async_add_entities(entities)


class AneoMobilityChargingSwitch(AneoMobilityEntity, SwitchEntity):
    """Switch to control charging start/stop."""

    _attr_translation_key = "charging_control"

    def __init__(self, coordinator, config_entry, charger_id):
        """Initialize the charging control switch."""
        super().__init__(coordinator, config_entry, charger_id)

    @property
    def is_on(self) -> bool:
        """Return true if charging is active."""
        if not self.coordinator.data or self._charger_id not in self.coordinator.data:
            return False

        charger_data = self.coordinator.data[self._charger_id]
        state = charger_data.get("state", {})

        # Check socket status - "Charging" or "SuspendedEV" means charging session is active
        sockets = state.get("sockets", [])
        if sockets:
            socket_status = sockets[0].get("status", "")
            # Charging session is active if status is Charging, SuspendedEV, or Finishing
            return socket_status in ["Charging", "SuspendedEV", "Finishing"]

        return False

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Start charging."""
        if not self.coordinator.data or self._charger_id not in self.coordinator.data:
            raise HomeAssistantError("Charger data not available")

        charger_data = self.coordinator.data[self._charger_id]
        subscription = charger_data.get("subscription", {})
        subscription_id = subscription.get("id")

        if not subscription_id:
            raise HomeAssistantError("Subscription ID not found")

        client = self.hass.data[DOMAIN][self.config_entry.entry_id]["client"]

        try:
            await client.start_charging(
                charger_id=self._charger_id,
                socket_id=1,
                subscription_id=subscription_id
            )
            # Request coordinator refresh to update state
            await self.coordinator.async_request_refresh()
        except Exception as err:
            _LOGGER.error("Failed to start charging: %s", err)
            raise HomeAssistantError(f"Failed to start charging: {err}") from err

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Stop charging."""
        if not self.coordinator.data or self._charger_id not in self.coordinator.data:
            raise HomeAssistantError("Charger data not available")

        charger_data = self.coordinator.data[self._charger_id]
        subscription = charger_data.get("subscription", {})
        subscription_id = subscription.get("id")

        if not subscription_id:
            raise HomeAssistantError("Subscription ID not found")

        client = self.hass.data[DOMAIN][self.config_entry.entry_id]["client"]

        try:
            await client.stop_charging(
                charger_id=self._charger_id,
                socket_id=1,
                subscription_id=subscription_id
            )
            # Request coordinator refresh to update state
            await self.coordinator.async_request_refresh()
        except Exception as err:
            _LOGGER.error("Failed to stop charging: %s", err)
            raise HomeAssistantError(f"Failed to stop charging: {err}") from err


class AneoMobilityCableLockSwitch(AneoMobilityEntity, SwitchEntity):
    """Switch to control cable lock."""

    _attr_translation_key = "cable_lock"

    def __init__(self, coordinator, config_entry, charger_id):
        """Initialize the cable lock switch."""
        super().__init__(coordinator, config_entry, charger_id)

    @property
    def is_on(self) -> bool:
        """Return true if cable is locked."""
        if not self.coordinator.data or self._charger_id not in self.coordinator.data:
            return False

        charger_data = self.coordinator.data[self._charger_id]
        state = charger_data.get("state", {})

        return state.get("isCableLockedPermanently", False)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Lock the cable."""
        client = self.hass.data[DOMAIN][self.config_entry.entry_id]["client"]

        try:
            await client.set_cable_lock(
                charger_id=self._charger_id,
                socket_id=1,
                locked=True
            )
            # Request coordinator refresh to update state
            await self.coordinator.async_request_refresh()
        except Exception as err:
            _LOGGER.error("Failed to lock cable: %s", err)
            raise HomeAssistantError(f"Failed to lock cable: {err}") from err

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Unlock the cable."""
        client = self.hass.data[DOMAIN][self.config_entry.entry_id]["client"]

        try:
            await client.set_cable_lock(
                charger_id=self._charger_id,
                socket_id=1,
                locked=False
            )
            # Request coordinator refresh to update state
            await self.coordinator.async_request_refresh()
        except Exception as err:
            _LOGGER.error("Failed to unlock cable: %s", err)
            raise HomeAssistantError(f"Failed to unlock cable: {err}") from err
