"""Factory gates: eligibility and effective configuration (tasks 2.5, 4.1, 4.2, 7.2)."""

from __future__ import annotations

import pytest

from custom_components.vtherm_auto_start_stop.const import (
    LEVEL_SLOW,
    STOP_MODE_OFF,
)
from custom_components.vtherm_auto_start_stop.factory import (
    AutoStartStopManagerFactory,
    ineligibility_reason,
    thermostat_type,
)

VT_UNIQUE_ID = "vtherm-uid-1"


class RuntimeThermostat:
    """The runtime facts the factory reads from a thermostat."""

    def __init__(
        self, unique_id=VT_UNIQUE_ID, thermostat_type="thermostat_over_climate"
    ):
        self.unique_id = unique_id
        self.name = "Thermostat"
        self.entry_infos = {"thermostat_type": thermostat_type}
        self.has_valve_regulation = False


@pytest.mark.parametrize(
    ("kind", "has_valve", "expected"),
    [
        ("thermostat_over_climate", False, None),
        ("thermostat_over_climate", True, "valve_regulation"),
        ("thermostat_over_switch", False, "not_over_climate"),
        ("thermostat_over_valve", False, "not_over_climate"),
        (None, False, "not_over_climate"),
    ],
)
def test_ineligibility_reason(kind, has_valve, expected):
    """The two rules are the ones the config flow reports."""
    thermostat = RuntimeThermostat(thermostat_type=kind)
    thermostat.has_valve_regulation = has_valve
    assert ineligibility_reason(thermostat) == expected


def test_thermostat_type_handles_a_missing_entry_infos():
    class NoInfos:
        unique_id = VT_UNIQUE_ID
        name = "Thermostat"

    assert thermostat_type(NoInfos()) is None


def test_supports_requires_an_over_climate_thermostat(fake_hass, add_global_entry):
    """A thermostat of another type gains no support (task 2.4/4.2)."""
    add_global_entry()
    factory = AutoStartStopManagerFactory(fake_hass)
    assert factory.supports(RuntimeThermostat()) is True
    assert (
        factory.supports(RuntimeThermostat(thermostat_type="thermostat_over_switch"))
        is False
    )


@pytest.mark.parametrize("enabled", [False, True])
def test_supports_refuses_a_valve_regulated_thermostat(
    fake_hass, add_global_entry, enabled
):
    add_global_entry(enabled=enabled)
    thermostat = RuntimeThermostat()
    thermostat.has_valve_regulation = True
    assert AutoStartStopManagerFactory(fake_hass).supports(thermostat) is False


def test_supports_requires_an_effective_configuration(fake_hass):
    """No global and no dedicated instance: nothing is attached (task 4.1)."""
    factory = AutoStartStopManagerFactory(fake_hass)
    assert factory.supports(RuntimeThermostat()) is False


@pytest.mark.parametrize("enabled", [False, True])
def test_supports_accepts_a_disabled_configuration(
    fake_hass, add_global_entry, add_dedicated_entry, enabled
):
    """Configuration presence, not the enable state, controls attachment."""
    add_global_entry(enabled=not enabled)
    add_dedicated_entry(enabled=enabled)
    assert AutoStartStopManagerFactory(fake_hass).supports(RuntimeThermostat()) is True


def test_supports_accepts_a_dedicated_instance(fake_hass, add_dedicated_entry):
    add_dedicated_entry()
    assert AutoStartStopManagerFactory(fake_hass).supports(RuntimeThermostat()) is True


def test_ineligibility_is_reported_with_its_reason(fake_hass, add_global_entry, caplog):
    """Task 4.2: the log entry names the reason."""
    add_global_entry()
    thermostat = RuntimeThermostat(thermostat_type="thermostat_over_switch")
    with caplog.at_level("INFO"):
        AutoStartStopManagerFactory(fake_hass).supports(thermostat)
    assert "not_over_climate" in caplog.text


def test_supports_returns_false_after_reconfiguration(
    fake_hass, add_global_entry, add_dedicated_entry
):
    """Task 7.2: a thermostat reconfigured into an ineligible state loses support."""
    add_global_entry()
    add_dedicated_entry(level=LEVEL_SLOW, stop_mode=STOP_MODE_OFF)
    factory = AutoStartStopManagerFactory(fake_hass)
    thermostat = RuntimeThermostat()
    assert factory.supports(thermostat) is True

    # The thermostat is reconfigured by the core: the factory re-checks the
    # runtime facts on every load, so no manager is created anymore.
    thermostat.entry_infos = {"thermostat_type": "thermostat_over_switch"}
    assert factory.supports(thermostat) is False


def test_factory_name_is_the_stable_name(fake_hass):
    assert AutoStartStopManagerFactory(fake_hass).name == "auto_start_stop"
