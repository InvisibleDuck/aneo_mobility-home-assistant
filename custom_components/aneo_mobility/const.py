"""Component constants."""

DOMAIN = "aneo_mobility"

INTEGRATION_VERSION = "0.0.1"

CONFIG_VERSION = 1

# ENTITY_TYPES = ["sensor", "binary_sensor", "switch", "button", "number", "time"]
ENTITY_TYPES = ["sensor", "binary_sensor", "switch"]

DATA_CLIENT = "client"

DATA_COORDINATORS = "coordinators"

DATA_OPTIONS = "options"

COORDINATOR_CHARGER_STATE = 0

COORDINATOR_PRICE_DATA = 1

DEFAULT_INTERVAL_CHARGER_STATE = 0.5

DEFAULT_INTERVAL_PRICE_DATA = 60
