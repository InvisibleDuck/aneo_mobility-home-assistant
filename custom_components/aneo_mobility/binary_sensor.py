"""Platform for sensor integration."""

from __future__ import annotations

import logging

from homeassistant import config_entries, core
from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)

from .base import AneoMobilityEntity
from .const import COORDINATOR_CHARGER_STATE, DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: core.HomeAssistant,
    config_entry: config_entries.ConfigEntry,
    async_add_entities,
):
    """Set up binary sensors from a config entry."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id]["coordinators"][
        COORDINATOR_CHARGER_STATE
    ]

    # Get all chargers from coordinator data
    if coordinator.data:
        sensors = []
        for charger_id, charger_data in coordinator.data.items():
            sensors.extend(
                [
                    CableLockedBinarySensor(coordinator, config_entry, charger_id),
                    ChargingBinarySensor(coordinator, config_entry, charger_id),
                    CarConnectedBinarySensor(coordinator, config_entry, charger_id),
                ]
            )
        async_add_entities(sensors, update_before_add=True)


class CableLockedBinarySensor(AneoMobilityEntity, BinarySensorEntity):
    """Binary sensor for if cable is locked."""

    _attr_translation_key = "cable_locked"
    _attr_icon = "mdi:lock-outline"
    _attr_device_class = BinarySensorDeviceClass.LOCK

    def __init__(self, coordinator, config_entry, charger_id):
        """Initialize the sensor."""
        super().__init__(
            coordinator, config_entry, charger_id
        )  # ← Must have charger_id!

    @property
    def is_on(self) -> bool | None:
        """Return if cable is locked."""
        if self.coordinator.data is None:
            return None

        charger_data = self.coordinator.data.get(self._charger_id)
        if not charger_data:
            return None

        state = charger_data.get("state", {})
        # Note: isCableLockedPermanently = True means locked, so invert for "unlocked" state
        return not state.get("isCableLockedPermanently", False)


class ChargingBinarySensor(AneoMobilityEntity, BinarySensorEntity):
    """Binary sensor for charger charge state."""

    _attr_translation_key = "charging"
    _attr_icon = "mdi:battery-charging-100"
    _attr_device_class = BinarySensorDeviceClass.BATTERY_CHARGING

    def __init__(self, coordinator, config_entry, charger_id):
        """Initialize the sensor."""
        super().__init__(
            coordinator, config_entry, charger_id
        )  # ← Must have charger_id!

    @property
    def is_on(self) -> bool | None:
        """Return if charger is actively charging."""
        if self.coordinator.data is None:
            return None

        charger_data = self.coordinator.data.get(self._charger_id)
        if not charger_data:
            return None

        state = charger_data.get("state", {})
        sockets = state.get("sockets", [])

        if not sockets:
            return None

        status = sockets[0].get("status")
        return status == "Charging"


class CarConnectedBinarySensor(AneoMobilityEntity, BinarySensorEntity):
    """Binary sensor for car connection status."""

    _attr_translation_key = "car_connected"
    _attr_icon = "mdi:ev-plug-type2"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(self, coordinator, config_entry, charger_id):
        """Initialize the sensor."""
        super().__init__(
            coordinator, config_entry, charger_id
        )  # ← Must have charger_id!

    @property
    def is_on(self) -> bool | None:
        """Return if car is connected to charger."""
        if self.coordinator.data is None:
            return None

        charger_data = self.coordinator.data.get(self._charger_id)
        if not charger_data:
            return None

        state = charger_data.get("state", {})
        sockets = state.get("sockets", [])

        if not sockets:
            return None

        status = sockets[0].get("status")
        return status in ("Charging", "Preparing", "Finishing", "SuspendedCAR")
