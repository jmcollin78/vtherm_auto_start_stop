"""The two parameter number entities (tasks 3.1, 3.2, 3.3)."""

from __future__ import annotations

from unittest.mock import Mock

import pytest
from homeassistant.components.number import NumberMode
from homeassistant.exceptions import ServiceValidationError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.vtherm_auto_start_stop.const import (
    CONF_ENABLED,
    CONF_ERROR_THRESHOLD,
    CONF_LEVEL,
    CONF_STOP_MODE,
    CONF_VTHERM_UNIQUE_ID,
    DATA_ENTRIES,
    DATA_MANAGERS,
    DOMAIN,
    DT_MIN_MAX_VALUE,
    DT_MIN_MIN_VALUE,
    ERROR_THRESHOLD_MAX_VALUE,
    ERROR_THRESHOLD_MIN_VALUE,
    ERROR_THRESHOLD_STEP,
    LEVEL_FAST,
    LEVEL_PERSONNALISE,
    LEVEL_SLOW,
    STOP_MODE_OFF,
)
from custom_components.vtherm_auto_start_stop.manager import AutoStartStopManager
from custom_components.vtherm_auto_start_stop.number import (
    AutoStartStopDtMinNumber,
    AutoStartStopErrorThresholdNumber,
)
from custom_components.vtherm_auto_start_stop.registry import control_state
from tests.conftest import FakeThermostat

THERMOSTAT_UID = "thermostat"


@pytest.fixture
async def numbers(hass, monkeypatch):
    """Attach both parameter numbers to a started manager."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_VTHERM_UNIQUE_ID: THERMOSTAT_UID,
            CONF_ENABLED: True,
            CONF_LEVEL: LEVEL_SLOW,
            CONF_STOP_MODE: STOP_MODE_OFF,
        },
    )
    entry.add_to_hass(hass)
    hass.data[DOMAIN] = {
        DATA_ENTRIES: {entry.entry_id: dict(entry.data)},
        DATA_MANAGERS: {},
    }
    thermostat = FakeThermostat(hass, THERMOSTAT_UID)
    manager = AutoStartStopManager(thermostat, hass)
    manager.post_init({})
    # The switch and the stop-mode select restore first in the real setup and
    # are what makes the manager ready; the numbers then join them.
    state = control_state(hass, THERMOSTAT_UID)
    state.enabled, state.stop_mode = True, STOP_MODE_OFF
    manager.restore_entity_state(True, STOP_MODE_OFF)

    dt_entity = AutoStartStopDtMinNumber(hass, entry, THERMOSTAT_UID)
    threshold_entity = AutoStartStopErrorThresholdNumber(hass, entry, THERMOSTAT_UID)
    entities = []
    for index, entity in enumerate((dt_entity, threshold_entity)):
        entity.hass = hass
        entity.entity_id = f"number.control_{index}"
        monkeypatch.setattr(entity, "async_write_ha_state", Mock())
        await entity.async_added_to_hass()
        entities.append(entity)
    yield entry, thermostat, manager, dt_entity, threshold_entity
    for entity in entities:
        await entity.async_will_remove_from_hass()


def test_both_numbers_are_configuration_controls(numbers):
    """Task 3.1: the two parameters are configuration entities."""
    _, _, _, dt_entity, threshold_entity = numbers
    for entity in (dt_entity, threshold_entity):
        assert entity.mode == NumberMode.BOX


def test_bounds_and_steps(numbers):
    """Task 3.1: the bounds and steps are the ones the schema documents."""
    _, _, _, dt_entity, threshold_entity = numbers
    assert dt_entity.native_min_value == DT_MIN_MIN_VALUE
    assert dt_entity.native_max_value == DT_MIN_MAX_VALUE
    assert dt_entity.native_step == 1
    assert threshold_entity.native_min_value == ERROR_THRESHOLD_MIN_VALUE
    assert threshold_entity.native_max_value == ERROR_THRESHOLD_MAX_VALUE
    assert threshold_entity.native_step == ERROR_THRESHOLD_STEP


def test_native_value_reads_the_seed(numbers):
    """The value comes from the restore cascade, i.e. the seed at first boot."""
    _, _, _, dt_entity, threshold_entity = numbers
    assert dt_entity.native_value == 30.0
    assert threshold_entity.native_value == 10.0


async def test_writing_dt_min_keeps_the_other_parameter(numbers):
    """D5: writing one parameter sends the *current* value of the other."""
    _, _, manager, dt_entity, _ = numbers
    await dt_entity.async_set_native_value(45)

    assert manager.dt_min == 45
    assert manager.error_threshold == 10.0
    assert manager.level == LEVEL_PERSONNALISE
    assert dt_entity.native_value == 45.0


async def test_writing_the_threshold_keeps_the_other_parameter(numbers):
    _, _, manager, _, threshold_entity = numbers
    await threshold_entity.async_set_native_value(25)

    assert manager.dt_min == 30.0
    assert manager.error_threshold == 25
    assert manager.level == LEVEL_PERSONNALISE
    assert threshold_entity.native_value == 25


async def test_writing_the_named_pair_derives_the_named_level(numbers):
    """A pair matching a named level is reported as that level, not custom."""
    _, _, manager, dt_entity, threshold_entity = numbers
    await dt_entity.async_set_native_value(DT_MIN_MIN_VALUE)
    await threshold_entity.async_set_native_value(ERROR_THRESHOLD_MIN_VALUE)

    # 5 / 1 is not a named pair: the level stays custom.
    assert manager.level == LEVEL_PERSONNALISE


@pytest.mark.parametrize(
    ("value", "attribute"),
    [
        (DT_MIN_MIN_VALUE - 1, "dt_entity"),
        (DT_MIN_MAX_VALUE + 1, "dt_entity"),
        (ERROR_THRESHOLD_MIN_VALUE - 1, "threshold_entity"),
        (ERROR_THRESHOLD_MAX_VALUE + 1, "threshold_entity"),
    ],
)
async def test_out_of_bounds_value_is_refused(numbers, value, attribute):
    """D7: an out-of-range write raises, never turns the entity unavailable."""
    _, thermostat, manager, dt_entity, threshold_entity = numbers
    entity = {"dt_entity": dt_entity, "threshold_entity": threshold_entity}[attribute]
    with pytest.raises(ServiceValidationError):
        await entity.async_set_native_value(value)
    assert manager.dt_min == 30.0
    assert manager.error_threshold == 10.0
    assert entity.available is True
    assert thermostat.refresh_requests == 0


async def test_boundary_values_are_accepted(numbers):
    _, _, manager, dt_entity, threshold_entity = numbers
    await dt_entity.async_set_native_value(DT_MIN_MIN_VALUE)
    await threshold_entity.async_set_native_value(ERROR_THRESHOLD_MAX_VALUE)
    assert manager.dt_min == DT_MIN_MIN_VALUE
    assert manager.error_threshold == ERROR_THRESHOLD_MAX_VALUE


async def test_missing_entry_is_reported(numbers, hass, monkeypatch):
    """An orphaned entity cannot write into a runtime that no longer exists."""
    _, _, manager, dt_entity, _ = numbers
    monkeypatch.setattr(hass.config_entries, "async_get_entry", lambda entry_id: None)
    with pytest.raises(ServiceValidationError):
        await dt_entity.async_set_native_value(45)
    assert manager.dt_min == 30.0


async def test_entities_become_available_once_the_manager_is_ready(numbers):
    """A parameter entity is available as soon as it has a value and a manager."""
    _, _, _, dt_entity, threshold_entity = numbers
    assert dt_entity.available is True
    assert threshold_entity.available is True
