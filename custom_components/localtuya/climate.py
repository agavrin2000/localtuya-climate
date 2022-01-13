"""Platform to locally control Tuya-based climate devices."""
import logging
from functools import partial

import voluptuous as vol
from homeassistant.components.climate import (
    DEFAULT_MAX_TEMP,
    DEFAULT_MIN_TEMP,
    ClimateEntity,
)
from homeassistant.components.climate.const import (  
    DOMAIN,
    HVAC_MODE_AUTO,
    HVAC_MODE_HEAT,
    HVAC_MODE_OFF,
    CURRENT_HVAC_IDLE,
    CURRENT_HVAC_OFF,
    CURRENT_HVAC_HEAT,
    SUPPORT_TARGET_TEMPERATURE,
    SUPPORT_TARGET_TEMPERATURE_RANGE,
)
from homeassistant.const import (
    ATTR_TEMPERATURE,
    PRECISION_HALVES,
    PRECISION_TENTHS,
    PRECISION_WHOLE,
    TEMP_CELSIUS,
    TEMP_FAHRENHEIT,
    STATE_OFF,
    STATE_ON,
)

from .common import LocalTuyaEntity, async_setup_entry
from .const import (
    CONF_CURRENT_TEMPERATURE_DP,
    CONF_HVAC_MODE_DP,
    CONF_MAX_TEMP_DP,
    CONF_MIN_TEMP_DP,
    CONF_TARGET_TEMPERATURE_DP,
    CONF_HVAC_ACTION_DP,
    CONF_PRECISION,
    CONF_CHILD_LOCK_DP,
)

_LOGGER = logging.getLogger(__name__)

DEFAULT_TEMPERATURE_UNIT = TEMP_CELSIUS
DEFAULT_PRECISION = PRECISION_TENTHS

HVAC_MODE_NAMES = {
    HVAC_MODE_AUTO: 'Program',
    HVAC_MODE_HEAT: 'Manual'
}
def flow_schema(dps):
    """Return schema used in config flow."""
    return {
        vol.Required(CONF_TARGET_TEMPERATURE_DP): vol.In(dps),
        vol.Required(CONF_CURRENT_TEMPERATURE_DP): vol.In(dps),
        vol.Optional(CONF_HVAC_MODE_DP): vol.In(dps),
        vol.Optional(CONF_HVAC_ACTION_DP): vol.In(dps),
        vol.Optional(CONF_MAX_TEMP_DP): vol.In(dps),
        vol.Optional(CONF_MIN_TEMP_DP): vol.In(dps),
        vol.Optional(CONF_PRECISION): vol.In(
            [PRECISION_WHOLE, PRECISION_HALVES, PRECISION_TENTHS]
        ),
        vol.Optional(CONF_CHILD_LOCK_DP): vol.In(dps),
    }

class LocaltuyaClimate(LocalTuyaEntity, ClimateEntity):
    """Tuya climate device."""

    def __init__(
        self,
        device,
        config_entry,
        dp_id,
        **kwargs,
    ):
        """Initialize a new LocaltuyaClimate."""
        super().__init__(device, config_entry, dp_id, _LOGGER, **kwargs)
        self._state = None
        self._hvac_mode = None # Initial HVAC mode
        self._precision = self._config.get(CONF_PRECISION, DEFAULT_PRECISION)
        self._temperature_unit = DEFAULT_TEMPERATURE_UNIT
        self._child_lock = False
        self._hvac_action = CURRENT_HVAC_IDLE # Initial HVAC action
        self._min_temp = DEFAULT_MIN_TEMP
        self._max_temp = DEFAULT_MAX_TEMP
        print("Initialized climate [{}]".format(self.name))
 
    @property
    def supported_features(self) -> int:
        """Flag supported features."""
        supported_features = 0
        if self.has_config(CONF_TARGET_TEMPERATURE_DP):
            supported_features = supported_features | SUPPORT_TARGET_TEMPERATURE
        return supported_features

    def child_lock(self) -> bool:
        """Return the child_lock status."""
        return self._child_lock

    @property
    def precision(self) -> float:
        """Return the precision of the system."""
        return self._precision

    @property
    def temperature_unit(self) -> str:
        """Return the unit of measurement used by the platform."""
        return TEMP_CELSIUS

    @property
    def hvac_mode(self) -> str:
        """Return current operation ie. heat, cool, idle."""
        return self._hvac_mode

    @property
    def hvac_modes(self):
        """List of available operation modes."""
        return [HVAC_MODE_OFF, HVAC_MODE_AUTO, HVAC_MODE_HEAT]

    @property
    def current_temperature(self) -> float:
        """Return the current temperature."""
        return self._current_temperature

    @property
    def target_temperature(self) -> float:
        """Return the temperature we try to reach."""
        return self._target_temperature

    async def async_set_temperature(self, **kwargs):
        """Set new target temperature."""
        if ATTR_TEMPERATURE in kwargs and self.has_config(CONF_TARGET_TEMPERATURE_DP):
            temperature = round(kwargs[ATTR_TEMPERATURE] / self._precision)
            await self._device.set_dp(temperature, self._config[CONF_TARGET_TEMPERATURE_DP])

    async def async_set_hvac_mode(self, hvac_mode):
        """Set new target operation mode."""
        # Do nothing if new mode = current mode
        if self._hvac_mode == hvac_mode:
            return

        if  hvac_mode == HVAC_MODE_OFF:
            await self._device.set_dp(False, self._dp_id)
            return

        # Turn on thermostat before set new mode
        if self._hvac_mode == HVAC_MODE_OFF:
            await self._device.set_dp(True, self._dp_id)
        if self.has_config(CONF_HVAC_MODE_DP):
            await self._device.set_dp(HVAC_MODE_NAMES[hvac_mode], self._config[CONF_HVAC_MODE_DP])

    async def async_set_child_lock(self, child_lock):
        """Set child lock."""
        if self.has_config(CONF_CHILD_LOCK_DP):
            await self._device.set_dp(child_lock, self._config[CONF_CHILD_LOCK_DP])

    @property
    def min_temp(self):
        """Return the minimum temperature."""
        if self.has_config(CONF_MIN_TEMP_DP):
            return self.dps_conf(CONF_MIN_TEMP_DP)
        return DEFAULT_MIN_TEMP

    @property
    def max_temp(self):
        """Return the maximum temperature."""
        if self.has_config(CONF_MAX_TEMP_DP):
            return self.dps_conf(CONF_MAX_TEMP_DP)
        return DEFAULT_MAX_TEMP

    @property
    def hvac_action(self):
        """Return the current running hvac operation if supported.
        Need to be one of CURRENT_HVAC_*.   """
        return self._hvac_action

    def status_updated(self):
        """Device status was updated."""
        self._state = STATE_ON if self.dps(self._dp_id) else STATE_OFF

        if self.has_config(CONF_CHILD_LOCK_DP):
            self._child_lock = self.dps_conf(CONF_CHILD_LOCK_DP)
        else:
            self._child_lock = None

        self._target_temperature = self.dps_conf(CONF_TARGET_TEMPERATURE_DP) * self._precision
        self._current_temperature = self.dps_conf(CONF_CURRENT_TEMPERATURE_DP) * self._precision

        if self._state == STATE_OFF:
            self._hvac_mode = HVAC_MODE_OFF
        elif self.has_config(CONF_HVAC_MODE_DP):
                self._hvac_mode = HVAC_MODE_HEAT if self.dps_conf(CONF_HVAC_MODE_DP)==HVAC_MODE_NAMES[HVAC_MODE_HEAT] else HVAC_MODE_AUTO
        else:
            self._hvac_mode = HVAC_MODE_HEAT

        if self._state == STATE_OFF:
            self._hvac_action = = CURRENT_HVAC_OFF
        elif self.dps_conf(CONF_HVAC_ACTION_DP):
                self._hvac_action = CURRENT_HVAC_HEAT if self.dps_conf(CONF_HVAC_ACTION_DP) else CURRENT_HVAC_IDLE
        else:
            self._hvac_mode = CURRENT_HVAC_IDLE

async_setup_entry = partial(async_setup_entry, DOMAIN, LocaltuyaClimate, flow_schema)
