from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, CONF_URL
from homeassistant.data_entry_flow import FlowResult

from .api import AneoMobilityClient, CannotConnect, InvalidAuth
from .const import DOMAIN

DEFAULT_BASE_URL = "https://api.aneomobility.com"


STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_URL, default=DEFAULT_BASE_URL): str,
        vol.Required(CONF_USERNAME): str,  # email
        vol.Required(CONF_PASSWORD): str,
    }
)


def _entry_data_from_tokens(
    base_url: str, client: AneoMobilityClient
) -> dict[str, Any]:
    """Convert client tokens to entry.data format."""
    return {
        "base_url": base_url,
        **client.tokens,  # user_id, account_id, username, access_token, refresh_token, refresh_token_expires_at
    }


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            base_url = user_input[CONF_URL].rstrip("/")

            # Create client and authenticate
            client = AneoMobilityClient(self.hass, base_url)

            try:
                tokens = await client.authenticate(
                    username=user_input[CONF_USERNAME],
                    password=user_input[CONF_PASSWORD],
                )
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception:
                errors["base"] = "unknown"
            else:
                # Avoid duplicates: use subscription_id as unique_id
                await self.async_set_unique_id(tokens.user_id)
                self._abort_if_unique_id_configured()

                # Optionally: fetch subscription ID during setup
                try:
                    subscriptions = await client.get_subscriptions()
                    subscription_id = subscriptions[0]["id"] if subscriptions else None
                except Exception:
                    subscription_id = None

                entry_data = _entry_data_from_tokens(base_url, client)
                if subscription_id:
                    entry_data["subscription_id"] = subscription_id

                return self.async_create_entry(
                    title="Aneo Mobility Account",
                    data=entry_data,
                )

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_SCHEMA, errors=errors
        )

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> FlowResult:
        """Handle reauth flow when refresh token is invalid."""
        self._reauth_entry = self.hass.config_entries.async_get_entry(
            self.context["entry_id"]
        )
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            base_url = self._reauth_entry.data["base_url"]
            client = AneoMobilityClient(self.hass, base_url)

            try:
                tokens = await client.authenticate(
                    username=user_input[CONF_USERNAME],
                    password=user_input[CONF_PASSWORD],
                )
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception:
                errors["base"] = "unknown"
            else:
                # Update existing entry with new tokens and reload
                return self.async_update_reload_and_abort(
                    self._reauth_entry,
                    data_updates=_entry_data_from_tokens(base_url, client),
                )

        return self.async_show_form(
            step_id="reauth_confirm", data_schema=STEP_USER_SCHEMA, errors=errors
        )
