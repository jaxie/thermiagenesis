"""The ThermiaGenesis component."""
import asyncio
import logging
import time
from datetime import datetime
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.const import CONF_PORT
from homeassistant.const import CONF_TYPE
from homeassistant.helpers.typing import ConfigType
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.helpers.update_coordinator import UpdateFailed
from pythermiagenesis import ThermiaGenesis
import pythermiagenesis.const as thermiaconst

from .const import DOMAIN

PLATFORMS = ["sensor", "binary_sensor", "climate", "switch", "number"]

SCAN_INTERVAL = timedelta(seconds=30)
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config: ConfigType):
    """Set up the ThermiaGenesis component."""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Set up ThermiaGenesis from a config entry."""
    host = entry.data[CONF_HOST]
    port = entry.data[CONF_PORT]
    kind = entry.data[CONF_TYPE]

    coordinator = ThermiaGenesisDataUpdateCoordinator(
        hass, host=host, port=port, kind=kind
    )
    await coordinator.async_refresh()

    if not coordinator.last_update_success:
        raise ConfigEntryNotReady

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Unload a config entry."""
    unload_ok = all(
        await asyncio.gather(
            *[
                hass.config_entries.async_forward_entry_unload(entry, component)
                for component in PLATFORMS
            ]
        )
    )
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok


class ThermiaGenesisDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching ThermiaGenesis data from the heat pump."""

    def __init__(self, hass, host, port, kind):
        """Initialize."""
        self.thermia = ThermiaGenesis(
            host, port=port, kind=kind, delay=0.05, max_registers=16
        )
        self.kind = kind
        self.attributes = {}

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=SCAN_INTERVAL,
        )

    async def _async_update_data(self):
        """Update data via library."""
        data = {}
        try:
            start_time = time.time()
            registers = self.attributes.keys()
            data = await self.thermia.async_update(only_registers=registers)

            # Sync with physical display setting for internal immersion heater (Holding Reg 321)
            try:
                if not self.thermia._client.is_open():
                    self.thermia._client.open()
                reg_321 = self.thermia._client.read_holding_registers(321, 1)
                if reg_321 is not None and len(reg_321) > 0:
                    is_enabled_on_display = (reg_321[0] == 2)
                    data["holding_internal_immersion_heater_enable"] = reg_321[0]
                    current_coil = data.get(thermiaconst.ATTR_COIL_ENABLE_INTERNAL_ADDITIONAL_HEATER)
                    # The physical touchscreen (Register 321) is the master authority:
                    data[thermiaconst.ATTR_COIL_ENABLE_INTERNAL_ADDITIONAL_HEATER] = is_enabled_on_display

                    # If display and Coil 4 are out of sync (e.g. user toggled physical display), auto-sync Coil 4
                    if current_coil is not None and bool(current_coil) != is_enabled_on_display:
                        try:
                            self.thermia._client.write_single_coil(4, is_enabled_on_display)
                            _LOGGER.info(
                                "Auto-synced Coil 4 to %s to match physical display Register 321",
                                is_enabled_on_display,
                            )
                        except Exception as coil_err:
                            _LOGGER.debug("Failed to auto-sync Coil 4: %s", coil_err)
            except Exception as ex:
                _LOGGER.debug(f"Failed to read holding register 321: {ex}")

            _LOGGER.debug(data)
            end_time = time.time()
            _LOGGER.debug(
                f"{datetime.now()} Fetching heatpump data took {end_time - start_time} s"
            )

        except (ConnectionError) as error:
            raise UpdateFailed(error)
        return data

    async def _async_set_data(self, register, value):
        """Set data via library."""
        try:
            await self.thermia.async_set(register, value)
            if register == thermiaconst.ATTR_COIL_ENABLE_INTERNAL_ADDITIONAL_HEATER:
                # Also set Holding Register 321 so the physical display toggle updates
                try:
                    if not self.thermia._client.is_open():
                        self.thermia._client.open()
                    reg_val = 2 if value else 0
                    self.thermia._client.write_single_register(321, reg_val)
                    self.thermia._client.close()
                    _LOGGER.info(f"Synchronized Atlas physical display register 321 to {reg_val}")
                except Exception as ex:
                    _LOGGER.error(f"Failed to write holding register 321: {ex}")

            if self.data is not None:
                new_data = dict(self.data)
                new_data[register] = value
                if register == thermiaconst.ATTR_COIL_ENABLE_INTERNAL_ADDITIONAL_HEATER:
                    new_data["holding_internal_immersion_heater_enable"] = 2 if value else 0
                self.async_set_updated_data(new_data)
        except (ConnectionError) as error:
            raise UpdateFailed(error)
        return self.thermia.data

    def registerAttribute(self, attribute):
        if type(attribute) is list:
            for name in attribute:
                _LOGGER.info(f"Register attribute for update: {name}")
                self.attributes[name] = True
        else:
            _LOGGER.info(f"Register attribute for update: {attribute}")
            self.attributes[attribute] = True

    async def wantsRefresh(self, attribute):
        await self.coordinator.async_request_refresh()
