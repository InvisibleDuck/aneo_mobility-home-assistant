from __future__ import annotations

from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import logging
from typing import Any

import aiohttp
import async_timeout

from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.util import dt as dt_util

from .utils import redact

_LOGGER = logging.getLogger(__name__)


AUTH_PATH = "/api/account/authenticate"
REFRESH_PATH = "/api/account/token/refresh"
SUBSCRIPTIONS_PATH = "/api/subscription/v3/subscriptions"
TIMEOUT = 20
ACCESS_TOKEN_LIFETIME_MINUTES = 55  # Refresh 5 min before actual expiry (60min)
OSLO_TZ = dt_util.get_time_zone("Europe/Oslo")
FETCH_TOMORROW_FROM_HOUR = 20


class CannotConnect(Exception):
    pass


class InvalidAuth(Exception):
    pass


class InvalidRefreshToken(Exception):
    pass


@dataclass(frozen=True)
class TokenSet:
    user_id: str
    account_id: str
    username: str
    access_token: str
    access_token_expires_at: str  # ISO string - calculated locally (55min from now)
    refresh_token: str
    refresh_token_expires_at: str  # ISO string - from API response (1 month)


class AneoMobilityClient:
    def __init__(self, hass, base_url: str) -> None:
        self._hass = hass
        self._session = async_get_clientsession(hass)
        self._base_url = base_url.rstrip("/")

        self._user_id: str | None = None
        self._account_id: str | None = None
        self._username: str | None = None
        self._access_token: str | None = None
        self._access_token_expires_at: str | None = None
        self._refresh_token: str | None = None
        self._refresh_token_expires_at: str | None = None

    @property
    def tokens(self) -> dict[str, Any]:
        """For persisting into entry.data."""
        return {
            "user_id": self._user_id,
            "account_id": self._account_id,
            "username": self._username,
            "access_token": self._access_token,
            "access_token_expires_at": self._access_token_expires_at,
            "refresh_token": self._refresh_token,
            "refresh_token_expires_at": self._refresh_token_expires_at,
        }

    def load_tokens_from_entry(self, entry_data: dict[str, Any]) -> None:
        self._user_id = entry_data.get("user_id")
        self._account_id = entry_data.get("account_id")
        self._username = entry_data.get("username")
        self._access_token = entry_data.get("access_token")
        self._access_token_expires_at = entry_data.get("access_token_expires_at")
        self._refresh_token = entry_data.get("refresh_token")
        self._refresh_token_expires_at = entry_data.get("refresh_token_expires_at")

    def is_access_token_valid(self) -> bool:
        """Check if access token is still valid (not expired)."""
        if not self._access_token or not self._access_token_expires_at:
            return False

        try:
            expires_at = datetime.fromisoformat(
                self._access_token_expires_at.replace("Z", "+00:00")
            )
            return datetime.now(timezone.utc) < expires_at
        except (ValueError, AttributeError):
            return False

    async def authenticate(self, username: str, password: str) -> TokenSet:
        url = f"{self._base_url}{AUTH_PATH}"
        body = {"userName": username, "password": password}

        try:
            async with async_timeout.timeout(TIMEOUT):
                resp = await self._session.post(url, json=body)
        except (aiohttp.ClientError, TimeoutError) as err:
            raise CannotConnect(err) from err

        if resp.status in (401, 403):
            await resp.release()
            raise InvalidAuth(f"HTTP {resp.status}")

        try:
            resp.raise_for_status()
            data: dict[str, Any] = await resp.json()
        except aiohttp.ClientResponseError as err:
            raise CannotConnect(err) from err
        finally:
            await resp.release()

        # Calculate access token expiry locally (55 minutes from now)
        access_token_expires_at = (
            datetime.now(timezone.utc)
            + timedelta(minutes=ACCESS_TOKEN_LIFETIME_MINUTES)
        ).isoformat()

        tokens = TokenSet(
            user_id=data["id"],
            username=data["userName"],
            access_token=data["accessToken"],
            access_token_expires_at=access_token_expires_at,  # Calculated locally
            refresh_token=data["refreshToken"],
            refresh_token_expires_at=data[
                "refreshTokenExpiresAt"
            ],  # From API (1 month)
            account_id=data["accountId"],
        )
        self._apply_tokens(tokens)
        return tokens

    async def refresh(self) -> TokenSet:
        """POST refresh; API returns new tokens.

        Response format:
        {
          "accessToken": "...",
          "refreshToken": "...",
          "expiresAt": "2026-05-02T18:46:14.4136264Z"  # refresh token expiry (1 month)
        }
        """
        if not self._user_id or not self._refresh_token:
            raise InvalidRefreshToken("Missing user_id/refresh_token")

        url = f"{self._base_url}{REFRESH_PATH}"
        body = {"userId": self._user_id, "refreshToken": self._refresh_token}

        try:
            async with async_timeout.timeout(TIMEOUT):
                resp = await self._session.post(url, json=body)
        except (aiohttp.ClientError, TimeoutError) as err:
            raise CannotConnect(err) from err

        if resp.status in (401, 403):
            await resp.release()
            raise InvalidRefreshToken(f"HTTP {resp.status}")

        try:
            resp.raise_for_status()
            data: dict[str, Any] = await resp.json()
        except aiohttp.ClientResponseError as err:
            raise CannotConnect(err) from err
        finally:
            await resp.release()

        # Calculate access token expiry locally (55 minutes from now)
        access_token_expires_at = (
            datetime.now(timezone.utc)
            + timedelta(minutes=ACCESS_TOKEN_LIFETIME_MINUTES)
        ).isoformat()

        # Preserve existing user_id, account_id, username
        tokens = TokenSet(
            user_id=self._user_id,  # Keep existing
            username=self._username,  # Keep existing
            account_id=self._account_id,  # Keep existing
            access_token=data["accessToken"],
            access_token_expires_at=access_token_expires_at,  # Calculated locally (55min)
            refresh_token=data["refreshToken"],
            refresh_token_expires_at=data["expiresAt"],  # From API (1 month)
        )
        self._apply_tokens(tokens)
        return tokens

    async def get_subscriptions(self) -> list[dict[str, Any]]:
        """GET /api/subscription/v3/subscriptions with bearer token.

        Returns list of subscriptions with charger info.
        """
        if not self._access_token:
            raise InvalidAuth("Missing access token")

        url = f"{self._base_url}{SUBSCRIPTIONS_PATH}"
        headers = {"Authorization": f"Bearer {self._access_token}"}

        try:
            async with async_timeout.timeout(TIMEOUT):
                resp = await self._session.get(url, headers=headers)
                if resp.status in (401, 403):
                    raise InvalidAuth(f"HTTP {resp.status}")
                resp.raise_for_status()
                return await resp.json()
        except (aiohttp.ClientError, TimeoutError) as err:
            raise CannotConnect(err) from err
        finally:
            try:
                await resp.release()
            except Exception:
                pass

    async def get_charger_state(self, charger_id: str) -> dict[str, Any]:
        """GET /api/chargingpoint/{chargerId} with bearer token.

        Returns detailed charger state including socket status.
        """
        if not self._access_token:
            raise InvalidAuth("Missing access token")

        url = f"{self._base_url}/api/chargingpoint/{charger_id}"
        headers = {"Authorization": f"Bearer {self._access_token}"}

        try:
            async with async_timeout.timeout(TIMEOUT):
                resp = await self._session.get(url, headers=headers)
                if resp.status in (401, 403):
                    raise InvalidAuth(f"HTTP {resp.status}")
                resp.raise_for_status()
                return await resp.json()
        except (aiohttp.ClientError, TimeoutError) as err:
            raise CannotConnect(err) from err
        finally:
            try:
                await resp.release()
            except Exception:
                pass

    async def get_all_chargers_state(self) -> dict[str, dict[str, Any]]:
        """Get state for all chargers in user's subscriptions.

        Returns dict mapping charger_id -> charger state data.
        """
        subscriptions = await self.get_subscriptions()

        chargers_state = {}
        for subscription in subscriptions:
            charger_id = subscription.get("charger", {}).get("chargerId")
            if charger_id:
                try:
                    state = await self.get_charger_state(charger_id)
                    chargers_state[charger_id] = {
                        "subscription": subscription,
                        "state": state,
                    }
                except Exception as err:
                    _LOGGER.warning(
                        "Failed to get state for charger %s: %s",
                        redact(charger_id),
                        err,
                    )

        return chargers_state

    async def get_price_data(self, subscription_id: str) -> dict[str, Any]:
        """Get hourly prices for today and tomorrow for a subscription."""
        if not self._access_token:
            raise InvalidAuth("Missing access token")

        # Use Home Assistant local time (timezone-aware)
        now = dt_util.now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        tomorrow_start = today_start + timedelta(days=1)

        date_today = today_start.date().isoformat()
        date_tomorrow = tomorrow_start.date().isoformat()

        fetch_tomorrow = now.hour >= FETCH_TOMORROW_FROM_HOUR

        url_today = f"{self._base_url}/api/myprices/{subscription_id}/market-prices?date={date_today}"
        url_tomorrow = f"{self._base_url}/api/myprices/{subscription_id}/market-prices?date={date_tomorrow}"

        headers = {"Authorization": f"Bearer {self._access_token}"}

        try:
            async with async_timeout.timeout(TIMEOUT):
                # Fetch today's prices (always)
                _LOGGER.debug("Fetching prices for today (date=%s)", date_today)

                resp_today = await self._session.get(url_today, headers=headers)

                if resp_today.status in (401, 403):
                    try:
                        _LOGGER.error(
                            "Auth failed for price data (status %s)", resp_today.status
                        )
                    except Exception:
                        pass
                    await resp_today.release()
                    raise InvalidAuth(f"HTTP {resp_today.status}")

                resp_today.raise_for_status()
                prices_today = await resp_today.json()
                await resp_today.release()

                prices_tomorrow = {"prices": []}
                if fetch_tomorrow:
                    _LOGGER.debug(
                        "Fetching prices for tomorrow (date=%s)", date_tomorrow
                    )
                    resp_tomorrow = await self._session.get(
                        url_tomorrow, headers=headers
                    )
                    prices_tomorrow = await resp_tomorrow.json()

                    if resp_tomorrow.status in (401, 403):
                        try:
                            _LOGGER.error(
                                "Auth failed for price data (status %s)",
                                resp_tomorrow.status,
                            )
                        except Exception:
                            pass
                        await resp_tomorrow.release()
                        raise InvalidAuth(f"HTTP {resp_tomorrow.status}")

                    resp_tomorrow.raise_for_status()
                    prices_tomorrow = await resp_tomorrow.json()
                    await resp_tomorrow.release()
                else:
                    _LOGGER.debug(
                        "Skipping tomorrow prices fetch before %02d:00 Europe/Oslo",
                        FETCH_TOMORROW_FROM_HOUR,
                    )
        except (aiohttp.ClientError, TimeoutError) as err:
            raise CannotConnect(err) from err

        # Format prices
        current_hour = now.hour
        formatted_prices_today = self._format_prices(prices_today, today_start)

        if len(prices_tomorrow.get("prices", [])) == 0:
            formatted_prices_tomorrow = None
        else:
            formatted_prices_tomorrow = self._format_prices(
                prices_tomorrow, tomorrow_start
            )

        return {
            "current_price": formatted_prices_today[current_hour]["price"],
            "extra_attributes": {
                "today": formatted_prices_today,
                "tomorrow": formatted_prices_tomorrow,
            },
        }

    async def start_charging(
        self, charger_id: str, socket_id: int, subscription_id: str
    ) -> dict[str, Any]:
        """Start charging transaction.

        POST /api/chargingpoint/v3/transaction/start
        """
        if not self._access_token:
            raise InvalidAuth("Missing access token")

        url = f"{self._base_url}/api/chargingpoint/v3/transaction/start"
        headers = {"Authorization": f"Bearer {self._access_token}"}
        body = {
            "identifier": charger_id,
            "socketId": socket_id,
            "subscriptionId": subscription_id,
        }

        try:
            async with async_timeout.timeout(TIMEOUT):
                resp = await self._session.post(url, headers=headers, json=body)
                if resp.status in (401, 403):
                    raise InvalidAuth(f"HTTP {resp.status}")
                resp.raise_for_status()
                return await resp.json()
        except (aiohttp.ClientError, TimeoutError) as err:
            raise CannotConnect(err) from err
        finally:
            try:
                await resp.release()
            except Exception:
                pass

    async def stop_charging(
        self, charger_id: str, socket_id: int, subscription_id: str
    ) -> dict[str, Any]:
        """Stop charging transaction.

        POST /api/chargingpoint/v3/transaction/stop
        """
        if not self._access_token:
            raise InvalidAuth("Missing access token")

        url = f"{self._base_url}/api/chargingpoint/v3/transaction/stop"
        headers = {"Authorization": f"Bearer {self._access_token}"}
        body = {
            "identifier": charger_id,
            "socketId": socket_id,
            "subscriptionId": subscription_id,
        }

        try:
            async with async_timeout.timeout(TIMEOUT):
                resp = await self._session.post(url, headers=headers, json=body)
                if resp.status in (401, 403):
                    raise InvalidAuth(f"HTTP {resp.status}")
                resp.raise_for_status()
                return await resp.json()
        except (aiohttp.ClientError, TimeoutError) as err:
            raise CannotConnect(err) from err
        finally:
            try:
                await resp.release()
            except Exception:
                pass

    async def set_cable_lock(
        self, charger_id: str, socket_id: int, locked: bool
    ) -> dict[str, Any]:
        """Set cable lock state.

        POST /api/chargingpoint/v3/set-cable-lock
        """
        if not self._access_token:
            raise InvalidAuth("Missing access token")

        url = f"{self._base_url}/api/chargingpoint/v3/set-cable-lock"
        headers = {"Authorization": f"Bearer {self._access_token}"}
        body = {"chargerId": charger_id, "socketId": socket_id, "locked": locked}

        try:
            async with async_timeout.timeout(TIMEOUT):
                resp = await self._session.post(url, headers=headers, json=body)
                if resp.status in (401, 403):
                    raise InvalidAuth(f"HTTP {resp.status}")
                resp.raise_for_status()
                return await resp.json()
        except (aiohttp.ClientError, TimeoutError) as err:
            raise CannotConnect(err) from err
        finally:
            try:
                await resp.release()
            except Exception:
                pass

    def _format_prices(
        self, prices: dict[str, Any], input_datetime: datetime
    ) -> list[dict[str, Any]]:
        """Format prices into wanted format from Aneo format.

        Args:
            prices: API response with prices list
            input_datetime: Date to format prices for

        Returns:
            List of dicts with price, price_start, price_stop for each hour
        """
        from datetime import timedelta, datetime

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

    def _apply_tokens(self, tokens: TokenSet) -> None:
        self._user_id = tokens.user_id
        self._account_id = tokens.account_id
        self._username = tokens.username
        self._access_token = tokens.access_token
        self._access_token_expires_at = tokens.access_token_expires_at
        self._refresh_token = tokens.refresh_token
        self._refresh_token_expires_at = tokens.refresh_token_expires_at
