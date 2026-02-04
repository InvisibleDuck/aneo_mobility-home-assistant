"""Base class for all entities."""

from homeassistant.core import callback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN


class AneoMobilityEntity(CoordinatorEntity):
    """Base class for all AneoMobility entities."""

    _attr_has_entity_name = True

    def __init__(self, coordinator, config_entry, charger_id=None):
        """Initialize the entity."""
        super().__init__(coordinator)
        self.config_entry = config_entry
        self._charger_id = charger_id

        # Device info
        if charger_id:
            # Create device per charger
            charger_name = self._get_charger_name()
            self._attr_device_info = {
                "identifiers": {(DOMAIN, f"{config_entry.entry_id}_{charger_id}")},
                "name": f"{charger_name}",
                "manufacturer": "Aneo Mobility",
                "model": "EV Charger",
            }
        else:
            # For price sensor - attach to first charger or create generic device
            self._attr_device_info = {
                "identifiers": {(DOMAIN, config_entry.entry_id)},
                "name": config_entry.title,
                "manufacturer": "Aneo Mobility",
                "model": "Account",
            }

    def _get_charger_name(self) -> str:
        """Get friendly charger name from coordinator data."""
        if not self.coordinator.data or not self._charger_id:
            return f"Charger {self._charger_id}" if self._charger_id else "Unknown"

        charger_data = self.coordinator.data.get(self._charger_id, {})
        subscription = charger_data.get("subscription", {})

        # Try to get friendly name from subscription
        facility_name = subscription.get("chargingFacilityName")
        parking_lot = subscription.get("parkingLot", {}).get("name")

        if facility_name and parking_lot:
            return f"{facility_name} - {parking_lot}"
        elif facility_name:
            return facility_name
        elif parking_lot:
            return f"Parking {parking_lot}"
        else:
            return f"Charger {self._charger_id}"

    @property
    def unique_id(self):
        """Return unique ID of the entity."""
        if self._charger_id:
            return f"{self.config_entry.entry_id}_{self._charger_id}_{self._attr_translation_key}"
        else:
            return f"{self.config_entry.entry_id}_{self._attr_translation_key}"
