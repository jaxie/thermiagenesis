"""Test Thermia Genesis climate and sensor temperature filtering."""
from unittest.mock import MagicMock

from custom_components.thermiagenesis.climate import ThermiaClimateSensor
from custom_components.thermiagenesis.sensor import ThermiaGenericSensor, ThermiaHeatpumpSensor
from custom_components.thermiagenesis.const import UNIT_TEMPERATURE
import pythermiagenesis.const as thermiaconst


def test_climate_missing_room_sensor():
    """Test that missing room sensor (200.0 °C) results in None for current_temperature."""
    coordinator = MagicMock()
    coordinator.last_update_success = True
    coordinator.data = {
        thermiaconst.ATTR_INPUT_ROOM_TEMPERATURE_SENSOR: 200.0,
        thermiaconst.ATTR_HOLDING_COMFORT_WHEEL_SETTING: 19.0,
        thermiaconst.ATTR_COIL_ENABLE_HEAT: True,
        thermiaconst.ATTR_INPUT_FIRST_PRIORITISED_DEMAND: "No demand",
    }
    climate = ThermiaClimateSensor(coordinator, "heat", {})
    assert climate.current_temperature is None
    assert climate.target_temperature == 19.0

    # Test valid temperature
    coordinator.data[thermiaconst.ATTR_INPUT_ROOM_TEMPERATURE_SENSOR] = 21.5
    assert climate.current_temperature == 21.5


def test_sensor_missing_room_sensor():
    """Test that missing temperature sensor (200.0 °C) is marked unavailable and None."""
    coordinator = MagicMock()
    coordinator.last_update_success = True
    coordinator.data = {
        thermiaconst.ATTR_INPUT_ROOM_TEMPERATURE_SENSOR: 200.0,
    }
    sensor = ThermiaGenericSensor(coordinator, thermiaconst.ATTR_INPUT_ROOM_TEMPERATURE_SENSOR, {})
    assert sensor.state is None
    assert sensor.available is False

    # Test valid temperature
    coordinator.data[thermiaconst.ATTR_INPUT_ROOM_TEMPERATURE_SENSOR] = 22.0
    assert sensor.state == 22.0
    assert sensor.available is True
