"""Sensors. Same names, units, classes and signs as solar-dash's MQTT feed."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, UnitOfEnergy, UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from . import SolarDashConfigEntry
from .const import CONF_URL, DOMAIN

PARALLEL_UPDATES = 0

CENTS_PER_KWH = "c/kWh"
AUD = "AUD"


def _round1(value: float | None) -> float | None:
    return None if value is None else round(value, 1)


@dataclass(frozen=True, kw_only=True)
class SolarDashSensorDescription(SensorEntityDescription):
    """A sensor and how to read its value from a coordinator's data."""

    # Which coordinator feeds it: "live", "today" or "prices".
    source: str
    value_fn: Callable[[Any], Any]


def _power(key: str, field: str, transform: Callable[[float], float] = lambda w: w):
    """A live power sensor reading `field` of the inverter sample."""

    def value(sample: dict[str, Any]) -> float | None:
        raw = sample.get(field)
        return None if raw is None else _round1(transform(raw))

    return SolarDashSensorDescription(
        key=key,
        translation_key=key,
        source="live",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        suggested_display_precision=0,
        value_fn=value,
    )


def _energy(key: str, field: str) -> SolarDashSensorDescription:
    """A today-kWh sensor reading `field` of the `/api/daily` row."""
    return SolarDashSensorDescription(
        key=key,
        translation_key=key,
        source="today",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=2,
        value_fn=lambda today: (
            None if today.energy.get(field) is None else round(today.energy[field], 3)
        ),
    )


# Sign conventions (from `modbus::Sample`): grid_w is + importing, battery_w is
# + charging. Import and export are also split into never-negative sensors.
LIVE_SENSORS: tuple[SolarDashSensorDescription, ...] = (
    _power("solar_power", "pv_w"),
    _power("home_load", "load_w"),
    _power("grid_power", "grid_w"),
    _power("battery_power", "battery_w"),
    SolarDashSensorDescription(
        key="battery_soc",
        translation_key="battery_soc",
        source="live",
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        suggested_display_precision=0,
        value_fn=lambda s: _round1(s.get("soc_pct")),
    ),
    _power("grid_import", "grid_w", lambda w: max(w, 0.0)),
    _power("grid_export", "grid_w", lambda w: max(-w, 0.0)),
)

ENERGY_SENSORS: tuple[SolarDashSensorDescription, ...] = (
    _energy("today_grid_import", "import_kwh"),
    _energy("today_grid_export", "export_kwh"),
    _energy("today_solar", "pv_kwh"),
    _energy("today_battery_charge", "battery_charge_kwh"),
    _energy("today_battery_discharge", "battery_discharge_kwh"),
    _energy("today_home_use", "load_kwh"),
)

# Money: HA only allows state class "total" for monetary, so none is set (as in MQTT).
COST_SENSORS: tuple[SolarDashSensorDescription, ...] = (
    SolarDashSensorDescription(
        key="today_power_cost",
        translation_key="today_power_cost",
        source="today",
        device_class=SensorDeviceClass.MONETARY,
        native_unit_of_measurement=AUD,
        suggested_display_precision=2,
        value_fn=lambda today: today.power_cost,
    ),
    SolarDashSensorDescription(
        key="today_net_cost",
        translation_key="today_net_cost",
        source="today",
        device_class=SensorDeviceClass.MONETARY,
        native_unit_of_measurement=AUD,
        suggested_display_precision=2,
        value_fn=lambda today: today.net_cost,
    ),
)

PRICE_SENSORS: tuple[SolarDashSensorDescription, ...] = (
    SolarDashSensorDescription(
        key="amber_general_price",
        translation_key="amber_general_price",
        source="prices",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=CENTS_PER_KWH,
        suggested_display_precision=1,
        value_fn=lambda prices: prices.general,
    ),
    SolarDashSensorDescription(
        key="amber_feed_in_price",
        translation_key="amber_feed_in_price",
        source="prices",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=CENTS_PER_KWH,
        suggested_display_precision=1,
        # Already flipped to "earned" by the coordinator.
        value_fn=lambda prices: prices.feed_in,
    ),
    SolarDashSensorDescription(
        key="amber_descriptor",
        translation_key="amber_descriptor",
        source="prices",
        value_fn=lambda prices: prices.descriptor,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SolarDashConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Create only the sensors this solar-dash install has."""
    runtime = entry.runtime_data
    caps = runtime.capabilities
    coordinators: dict[str, DataUpdateCoordinator[Any]] = {
        "live": runtime.live,
        "today": runtime.today,
    }
    if runtime.prices is not None:
        coordinators["prices"] = runtime.prices

    descriptions: list[SolarDashSensorDescription] = []
    if caps.get("live"):
        descriptions += LIVE_SENSORS
    # Day totals come from the inverter samples (live) or iSolarCloud (history).
    if caps.get("live") or caps.get("history"):
        descriptions += ENERGY_SENSORS
    if caps.get("costs"):
        descriptions += COST_SENSORS
    if caps.get("prices"):
        descriptions += PRICE_SENSORS

    async_add_entities(
        SolarDashSensor(coordinators[d.source], entry, d) for d in descriptions
    )


class SolarDashSensor(CoordinatorEntity[DataUpdateCoordinator[Any]], SensorEntity):
    """One solar-dash value."""

    _attr_has_entity_name = True
    entity_description: SolarDashSensorDescription

    def __init__(
        self,
        coordinator: DataUpdateCoordinator[Any],
        entry: SolarDashConfigEntry,
        description: SolarDashSensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="solar-dash",
            manufacturer="solar-dash",
            model="solar-dash",
            configuration_url=entry.data[CONF_URL],
        )

    @property
    def native_value(self) -> Any:
        return self.entity_description.value_fn(self.coordinator.data)
