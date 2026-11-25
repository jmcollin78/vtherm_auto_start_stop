"""Config flow behaviour (tasks 2.2, 2.3, 2.4, 6.1, 6.2)."""

from __future__ import annotations

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.vtherm_auto_start_stop.const import (
    CONF_ENABLED,
    CONF_ERROR_THRESHOLD,
    CONF_LEVEL,
    CONF_DT_MIN,
    CONF_STOP_MODE,
    CONF_TARGET_ENTITY,
    CONF_VTHERM_UNIQUE_ID,
    DOMAIN,
    LEVEL_FAST,
    LEVEL_MEDIUM,
    LEVEL_PERSONNALISE,
    LEVEL_SLOW,
    STOP_MODE_DRY,
)
from custom_components.vtherm_auto_start_stop.models import entry_config

THERMOSTAT_ENTITY = "climate.thermostat"
THERMOSTAT_UNIQUE_ID = "vtherm-uid-1"


@pytest.fixture(autouse=True)
def custom_integrations(enable_custom_integrations):  # noqa: PT004
    """Load the custom component from this repository."""
    return enable_custom_integrations


@pytest.fixture(autouse=True)
def mock_versatile_thermostat(hass):
    """Mock the core integration the plugin declares as a dependency.

    The plugin only needs the core to be *loaded*: it talks to it through
    ``vtherm_api`` and the entity registry, never through its module internals.
    Mocking it keeps the flow tests focused on the plugin's own branches.
    """
    from pytest_homeassistant_custom_component.common import (
        MockModule,
        mock_integration,
        mock_platform,
    )

    mock_integration(hass, MockModule("versatile_thermostat"))
    mock_platform(hass, "versatile_thermostat.config_flow", None)
    return None


class MockModule:
    """A minimal integration module for the dependency mock."""

    def __init__(self, domain: str) -> None:
        self.domain = domain
        self.name = domain
        self.version = "0.0.0"
        self.dependencies: list[str] = []
        self.requirements: list[str] = []
        self.config_flow = False
        self.documentation = "https://example.com"
        self.issue_tracker = None
        self.iot_class = "local_polling"
        self.integration_type = "service"
        self.logger = None

    def async_setup_entry(self, *args, **kwargs):
        """Nothing to set up: the core is mocked."""

    async def async_unload_entry(self, *args, **kwargs):
        return True


def register_thermostat(
    hass: HomeAssistant, thermostat_type="over_climate", has_valve=False
):
    """Register a thermostat entity and its registry entry."""
    from homeassistant.helpers import entity_registry as er

    registry = er.async_get(hass)
    registry.async_get_or_create(
        "climate",
        "versatile_thermostat",
        THERMOSTAT_UNIQUE_ID,
        suggested_object_id="thermostat",
    )
    hass.states.async_set(
        THERMOSTAT_ENTITY,
        "heat",
        {
            "friendly_name": "Thermostat",
            "configuration": {
                "type": thermostat_type,
                "have_valve_regulation": has_valve,
            },
        },
    )


async def start_flow(hass: HomeAssistant):
    """Start a user flow."""
    return await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})


async def test_first_flow_is_the_global_branch(hass):
    """Task 2.2: with no entry, the flow goes straight to the global step."""
    register_thermostat(hass)
    result = await start_flow(hass)
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "global"
    assert CONF_ENABLED in result["data_schema"].schema


async def test_global_entry_is_created_and_unique(hass):
    """Task 2.2: a second global instance is refused."""
    register_thermostat(hass)
    result = await start_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_LEVEL: LEVEL_SLOW,
            CONF_STOP_MODE: STOP_MODE_DRY,
            CONF_ENABLED: True,
        },
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_LEVEL] == LEVEL_SLOW

    # A second global entry cannot be created: the unique id is the domain.
    second = await start_flow(hass)
    assert second["type"] == FlowResultType.FORM
    assert second["step_id"] == "thermostat"


async def test_additional_entry_opens_the_thermostat_selector(hass):
    """The dedicated flow has no intermediate intent menu."""
    MockConfigEntry(
        domain=DOMAIN,
        data={CONF_LEVEL: LEVEL_SLOW, CONF_STOP_MODE: STOP_MODE_DRY},
    ).add_to_hass(hass)
    register_thermostat(hass)
    result = await start_flow(hass)
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "thermostat"
    assert CONF_TARGET_ENTITY in result["data_schema"].schema


@pytest.mark.parametrize("thermostat_type", ["over_climate", "thermostat_over_climate"])
async def test_dedicated_entry_stores_the_thermostat_unique_id(hass, thermostat_type):
    """Task 2.3: the entry stores the thermostat unique id, not the entity id."""
    MockConfigEntry(
        domain=DOMAIN,
        data={CONF_LEVEL: LEVEL_SLOW, CONF_STOP_MODE: STOP_MODE_DRY},
    ).add_to_hass(hass)
    register_thermostat(hass, thermostat_type=thermostat_type)

    result = await start_flow(hass)
    assert result["step_id"] == "thermostat"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_TARGET_ENTITY: THERMOSTAT_ENTITY}
    )
    assert result["step_id"] == "thermostat_options"
    # The dedicated form exposes all detection fields (level + custom params).
    assert set(result["data_schema"].schema) == {
        CONF_LEVEL,
        CONF_DT_MIN,
        CONF_ERROR_THRESHOLD,
    }

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_LEVEL: LEVEL_FAST,
        },
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_VTHERM_UNIQUE_ID] == THERMOSTAT_UNIQUE_ID
    assert result["data"][CONF_LEVEL] == LEVEL_FAST
    assert CONF_ENABLED not in result["data"]
    assert CONF_STOP_MODE not in result["data"]


@pytest.mark.parametrize(
    ("thermostat_type", "has_valve", "error"),
    [
        ("over_switch", False, "not_over_climate"),
        ("thermostat_over_switch", False, "not_over_climate"),
        ("over_valve", False, "not_over_climate"),
        ("over_climate_valve", True, "not_over_climate"),
        ("thermostat_central_config", False, "not_over_climate"),
        ("over_climate", True, "valve_regulation"),
        ("thermostat_over_climate", True, "valve_regulation"),
    ],
)
async def test_ineligible_thermostat_reports_its_reason(
    hass, thermostat_type, has_valve, error
):
    """Task 2.4: the error names the reason."""
    MockConfigEntry(
        domain=DOMAIN,
        data={CONF_LEVEL: LEVEL_SLOW, CONF_STOP_MODE: STOP_MODE_DRY},
    ).add_to_hass(hass)
    register_thermostat(hass, thermostat_type=thermostat_type, has_valve=has_valve)

    result = await start_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_TARGET_ENTITY: THERMOSTAT_ENTITY}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "thermostat"
    assert result["errors"] == {CONF_TARGET_ENTITY: error}


@pytest.mark.parametrize("enabled", [False, True])
async def test_dedicated_parameters_can_be_edited(hass, enabled):
    """Only parameters are editable, retaining legacy fields for migration."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_VTHERM_UNIQUE_ID: THERMOSTAT_UNIQUE_ID,
            CONF_LEVEL: LEVEL_SLOW,
            CONF_STOP_MODE: STOP_MODE_DRY,
            CONF_ENABLED: not enabled,
        },
    )
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["step_id"] == "init"
    assert set(result["data_schema"].schema) == {
        CONF_LEVEL,
        CONF_DT_MIN,
        CONF_ERROR_THRESHOLD,
    }
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            CONF_LEVEL: LEVEL_FAST,
        },
    )
    await hass.async_block_till_done()
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert entry_config(entry)[CONF_LEVEL] == LEVEL_FAST
    assert entry_config(entry)[CONF_ENABLED] is (not enabled)
    assert entry_config(entry)[CONF_VTHERM_UNIQUE_ID] == THERMOSTAT_UNIQUE_ID


@pytest.mark.parametrize("enabled", [False, True])
async def test_dedicated_settings_do_not_expose_enable_or_mode(hass, enabled):
    MockConfigEntry(
        domain=DOMAIN,
        data={CONF_ENABLED: enabled},
    ).add_to_hass(hass)
    MockConfigEntry(
        domain=DOMAIN,
        data={CONF_VTHERM_UNIQUE_ID: "another-thermostat"},
        options={CONF_ENABLED: not enabled},
    ).add_to_hass(hass)
    register_thermostat(hass)

    result = await reach_thermostat_options(hass)
    defaults = result["data_schema"]({})
    assert set(defaults) == {CONF_LEVEL, CONF_DT_MIN, CONF_ERROR_THRESHOLD}


# ---------------------------------------------------------------------------
# Migration from the core configuration (tasks 6.1, 6.2)
# ---------------------------------------------------------------------------


def register_core_entry(hass: HomeAssistant, level: str) -> MockConfigEntry:
    """Register a thermostat owning a core config entry carrying a legacy level."""
    from homeassistant.helpers import entity_registry as er

    core_entry = MockConfigEntry(
        domain="versatile_thermostat",
        data={"thermostat_type": "thermostat_over_climate"},
        options={"auto_start_stop_level": level},
        unique_id=THERMOSTAT_UNIQUE_ID,
        entry_id="core-entry",
    )
    core_entry.add_to_hass(hass)

    registry = er.async_get(hass)
    registry.async_get_or_create(
        "climate",
        "versatile_thermostat",
        THERMOSTAT_UNIQUE_ID,
        suggested_object_id="thermostat",
        config_entry=core_entry,
    )
    hass.states.async_set(
        THERMOSTAT_ENTITY,
        "heat",
        {
            "friendly_name": "Thermostat",
            "configuration": {
                "type": "over_climate",
                "have_valve_regulation": False,
            },
        },
    )
    return core_entry


async def reach_thermostat_options(hass: HomeAssistant):
    """Walk the flow up to the dedicated values step."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    return await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_TARGET_ENTITY: THERMOSTAT_ENTITY}
    )


@pytest.mark.parametrize(
    ("thermostat_type", "regulation_mode", "error"),
    [
        ("thermostat_over_climate", None, None),
        ("thermostat_over_climate", "auto_regulation_valve", "valve_regulation"),
        ("thermostat_over_switch", None, "not_over_climate"),
    ],
)
async def test_eligibility_uses_core_entry_when_state_is_missing(
    hass, thermostat_type, regulation_mode, error
):
    """The stored thermostat type is still used before state publication."""
    MockConfigEntry(
        domain=DOMAIN,
        data={CONF_LEVEL: LEVEL_SLOW, CONF_STOP_MODE: STOP_MODE_DRY},
    ).add_to_hass(hass)
    core_entry = register_core_entry(hass, LEVEL_FAST)
    hass.config_entries.async_update_entry(
        core_entry,
        data={
            "thermostat_type": thermostat_type,
            "auto_regulation_mode": regulation_mode,
        },
    )
    hass.states.async_remove(THERMOSTAT_ENTITY)

    result = await reach_thermostat_options(hass)

    assert result["type"] == FlowResultType.FORM
    if error is None:
        assert result["step_id"] == "thermostat_options"
    else:
        assert result["step_id"] == "thermostat"
        assert result["errors"] == {CONF_TARGET_ENTITY: error}


async def test_legacy_level_seeds_the_dedicated_instance(hass):
    """Task 6.1: the migrated level replaces the plugin default."""
    MockConfigEntry(
        domain=DOMAIN,
        data={CONF_LEVEL: LEVEL_SLOW, CONF_STOP_MODE: STOP_MODE_DRY},
    ).add_to_hass(hass)
    register_core_entry(hass, LEVEL_FAST)

    result = await reach_thermostat_options(hass)
    assert result["step_id"] == "thermostat_options"
    schema = result["data_schema"].schema
    defaults = {
        str(key): key.default() if callable(key.default) else key.default
        for key in schema
    }
    assert defaults[CONF_LEVEL] == LEVEL_FAST


async def test_an_existing_dedicated_instance_is_not_overwritten(hass):
    """Task 6.2: an existing dedicated entry keeps its own level."""
    MockConfigEntry(
        domain=DOMAIN,
        data={CONF_LEVEL: LEVEL_SLOW, CONF_STOP_MODE: STOP_MODE_DRY},
    ).add_to_hass(hass)
    MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_VTHERM_UNIQUE_ID: THERMOSTAT_UNIQUE_ID,
            CONF_LEVEL: LEVEL_MEDIUM,
            CONF_STOP_MODE: STOP_MODE_DRY,
            CONF_ENABLED: True,
        },
        unique_id=f"{DOMAIN}-{THERMOSTAT_UNIQUE_ID}",
    ).add_to_hass(hass)
    register_core_entry(hass, LEVEL_FAST)

    # The dedicated entry already exists: the flow aborts instead of starting a
    # new instance seeded from the legacy level.
    result = await reach_thermostat_options(hass)
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "already_configured"


# ---------------------------------------------------------------------------
# Custom parameters (personnalise level)
# ---------------------------------------------------------------------------


async def test_custom_fields_always_visible_in_the_form(hass):
    """The dt_min / error_threshold selectors are shown at every level, not only personnalise.

    They are seeded with the plugin defaults (SLOW: 30 / 10) by default, but
    the user can read or edit them at any time. When the resulting level is a
    named one the algorithm ignores those values (resolve_params reads the
    named table), but they remain persisted in the entry so the user does not
    have to re-enter them on the next personnalise switch.
    """
    global_entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_LEVEL: LEVEL_SLOW,
            CONF_STOP_MODE: STOP_MODE_DRY,
            CONF_ENABLED: True,
        },
    )
    global_entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(global_entry.entry_id)
    assert result["step_id"] == "init"
    # Both custom fields are always visible, whatever the current level is.
    assert set(result["data_schema"].schema) == {
        CONF_LEVEL,
        CONF_STOP_MODE,
        CONF_ENABLED,
        CONF_DT_MIN,
        CONF_ERROR_THRESHOLD,
    }
    # The selectors are pre-filled with the plugin defaults (SLOW : 30 / 10).
    defaults = result["data_schema"]({})
    assert defaults[CONF_DT_MIN] == 30
    assert defaults[CONF_ERROR_THRESHOLD] == 10

    # Switching to personnalise and leaving the default values as-is:
    # they end up persisted on the entry (the selector sends them).
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            CONF_LEVEL: LEVEL_PERSONNALISE,
            CONF_STOP_MODE: STOP_MODE_DRY,
            CONF_ENABLED: True,
            CONF_DT_MIN: 30,
            CONF_ERROR_THRESHOLD: 10,
        },
    )
    await hass.async_block_till_done()

    config = entry_config(global_entry)
    assert config[CONF_LEVEL] == LEVEL_PERSONNALISE
    assert config[CONF_DT_MIN] == 30
    assert config[CONF_ERROR_THRESHOLD] == 10


async def test_custom_values_stay_in_the_entry_after_a_level_change(hass):
    """The custom keys stay in the entry across personnalise→medium→personnalise.

    Because the forms always expose the two selectors, changing the level from
    personnalise to a named one does NOT erase the custom values from the
    entry : they are still submitted with the (user-edited) values. resolve_params
    only reads them when the level is LEVEL_PERSONNALISE, so a named level
    ignores them without dropping them (design.md, decision C1).
    """
    global_entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_LEVEL: LEVEL_PERSONNALISE,
            CONF_STOP_MODE: STOP_MODE_DRY,
            CONF_ENABLED: True,
            CONF_DT_MIN: 45,
            CONF_ERROR_THRESHOLD: 25,
        },
    )
    global_entry.add_to_hass(hass)

    # personnalise → medium : the user resubmits the same values visible in the
    # form (45/25), so both keys remain in the options even at a named level.
    result = await hass.config_entries.options.async_init(global_entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            CONF_LEVEL: LEVEL_MEDIUM,
            CONF_STOP_MODE: STOP_MODE_DRY,
            CONF_ENABLED: True,
            CONF_DT_MIN: 45,
            CONF_ERROR_THRESHOLD: 25,
        },
    )
    await hass.async_block_till_done()
    assert entry_config(global_entry)[CONF_LEVEL] == LEVEL_MEDIUM
    # Custom values persist but are not applied at the named level.
    assert entry_config(global_entry)[CONF_DT_MIN] == 45
    assert entry_config(global_entry)[CONF_ERROR_THRESHOLD] == 25

    # medium → personnalise : the same visible values (45/25) are resubmitted,
    # and now the algorithm reads them.
    result = await hass.config_entries.options.async_init(global_entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            CONF_LEVEL: LEVEL_PERSONNALISE,
            CONF_STOP_MODE: STOP_MODE_DRY,
            CONF_ENABLED: True,
            CONF_DT_MIN: 45,
            CONF_ERROR_THRESHOLD: 25,
        },
    )
    await hass.async_block_till_done()

    config = entry_config(global_entry)
    assert config[CONF_LEVEL] == LEVEL_PERSONNALISE
    assert config[CONF_DT_MIN] == 45
    assert config[CONF_ERROR_THRESHOLD] == 25
    assert CONF_DT_MIN in global_entry.options
    assert CONF_ERROR_THRESHOLD in global_entry.options


@pytest.mark.parametrize(
    ("dt_min", "error_threshold", "in_range"),
    [
        (3, 0.5, False),  # below the lower bounds → rejected
        (200, 60, False),  # above the upper bounds → rejected
        (45, 25.0, True),  # within bounds → kept
    ],
)
async def test_custom_values_checked_against_the_selector_bounds(
    hass, dt_min, error_threshold, in_range
):
    """dt_min/error_threshold are enforced to [5,120] and [1,50].

    The NumberSelector schema rejects out-of-bounds values; in-range values
    are accepted and preserved.
    """
    from homeassistant.data_entry_flow import InvalidData

    global_entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_LEVEL: LEVEL_PERSONNALISE,
            CONF_STOP_MODE: STOP_MODE_DRY,
            CONF_ENABLED: True,
            CONF_DT_MIN: 45,
            CONF_ERROR_THRESHOLD: 25.0,
        },
    )
    global_entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(global_entry.entry_id)
    payload = {
        CONF_LEVEL: LEVEL_PERSONNALISE,
        CONF_STOP_MODE: STOP_MODE_DRY,
        CONF_ENABLED: True,
        CONF_DT_MIN: dt_min,
        CONF_ERROR_THRESHOLD: error_threshold,
    }
    if not in_range:
        with pytest.raises(InvalidData):
            await hass.config_entries.options.async_configure(
                result["flow_id"], payload
            )
        return

    await hass.config_entries.options.async_configure(result["flow_id"], payload)
    await hass.async_block_till_done()

    config = entry_config(global_entry)
    assert config[CONF_LEVEL] == LEVEL_PERSONNALISE
    assert config[CONF_DT_MIN] == dt_min
    assert config[CONF_ERROR_THRESHOLD] == error_threshold
