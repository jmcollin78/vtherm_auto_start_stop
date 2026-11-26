# Contributing to VTherm Auto Start/Stop

**[Contributors (EN)](CONTRIBUTING.md) · [Contributeurs (FR)](CONTRIBUTING-fr.md)** ·
[User documentation (EN)](README.md) · [Documentation utilisateur (FR)](README-fr.md)

This repository is **both** the OpenSpec hub and the full integration:
`custom_components/vtherm_auto_start_stop/` (code) and `tests/` live here, and
`openspec/` contains the specifications, change proposals and the archive.

> **Read this in order:** 1. Repository layout → 2. How the plugin talks to the
> core → 3. The mandatory OpenSpec workflow → 4. Design principles → 5. Coding
> & testing rules → 6. Adding documentation.

## 1. Repository layout

```
├── custom_components/vtherm_auto_start_stop/   # the integration
│   ├── __init__.py      # setup: global init, async_remove, reload orchestration
│   ├── const.py         # domain, levels, config keys, defaults
│   ├── models.py        # frozen/slots dataclasses (entries, params, snapshot)
│   ├── algorithm.py     # the pure-detection algorithm (no Home Assistant imports)
│   ├── manager.py       # detection manager: snapshots, state, per-level parameters
│   ├── registry.py      # thermostat registry + reload/registration coordination
│   ├── factory.py       # eligibility (supports()) + control creation
│   ├── config_flow.py   # the (single) configuration flow, global & dedicated
│   ├── select.py        # the Stop mode select entity
│   ├── entity.py        # shared base for the two control entities
│   ├── switch.py        # the Enable auto start/stop switch entity
│   ├── translations/{en,fr}.json  # texts (custom integrations ship finished files)
│   └── manifest.json
├── tests/                           # pytest suite (pure, no Home Assistant)
└── openspec/                        # the specification hub (see §3)
    ├── specs/                     # current capability specs (the source of truth)
    ├── changes/archive/           # completed + archived changes (history)
    └── changes/<change>/          # in-flight changes (delta + tasks)
```

Three of the four current capability specs live under `openspec/specs/`:
`auto-start-stop-plugin`, `auto-start-stop-delegation` and
`thermostat-runtime-api`. Treat **`openspec/specs/` as the single source of
truth for behaviour**; `openspec/changes/` only ever *describes deltas*.

## 2. How the plugin talks to the core

The plugin **never patches or subclasses** the Versatile Thermostat core. The
whole contract is a thin delegation API exposed by the `vtherm_api` package
(PyPI, pinned in `manifest.json`), implemented by the core.

```
                    ┌────────────────────────────────────────────┐
                    │  Versatile Thermostat core (jmcollin78)    │
                    │                                            │
   registers ─────► │  FeatureManager  ◄──►  InterfaceThermostat │
                    │  (per-thermostat   │     Runtime           │
                    │   FeatureInstance) │                       │
                    └──────────────┬─────┴───────────────────────┘
                                   │  vtherm_api (PyPI, pinned)
                    ┌──────────────▼─────────────────────────────┐
                    │  vtherm_auto_start_stop (this plugin)      │
                    │  register_feature_manager / async_start    │
                    │  InterfaceVThermAutoStartStop (adapter)     │
                    └────────────────────────────────────────────┘
```

What the plugin **consumes** (core → plugin):

- `InterfaceThermostatRuntime` — current snapshot data: `current_temp`,
  `target_temp`, `requested_hvac_mode`, `current_hvac_mode`.
- `has_valve_regulation: bool` — drives the valve-regulated exclusion (D14).
- `vtherm_hvac_modes: tuple` — available modes, drives the stop-mode select.
- `async_request_state_refresh()` — the one synchronous refresh the detector
  performs on a preset/target change (D16); the core is the only one that may
  call it, the plugin never schedules it.

What the plugin **injects** (plugin → core, via `InterfaceVThermAutoStartStop`):

- `is_active()` — the switch state; the core must consult it before
  accumulating or deciding.
- `get_stop_mode()` — the selected stop-mode value.
- `apply_stop_mode(mode) -> bool` — a **synchronous request-only** call: the
  core performs the HVAC-mode switch (or the switch-off when the value is an
  `off` mode) within the same loop run, never schedules it, never fails loudly.
- `has_accumulated_error` — read on reload (see §4, persistence).

The two capabilities that encode this contract live as specs:
`auto-start-stop-delegation` (the generic core side) and
`thermostat-runtime-api` (the concrete plugin side). **Any change to the API
surface must be proposed via an OpenSpec change** that updates those specs, and
ships as a coordinated triple (core + `vtherm_api` + this plugin).

### Eligibility and the `none`-level legacy (invariant I2–I6)

`factory.supports()` — and the dedicated config-flow selector — **only ever
offer** an `over_climate` thermostat **with no valve regulation**. The legacy
auto start/stop entity of the core (when `legacy_auto_start_stop_entity` is
non-null) is always offered as an extra item, so the migration path always has
a dedicated entry to seed from.

The historical `none` level is **no longer selectable**; any stored value that
still reads `none` is normalised to the default level (Slow) at load time.
`none` was never a stop mode, so no state migration is required. Code may keep
a historical constant for backwards compatibility, but it must never be
selected or written by the UI.

## 3. The mandatory OpenSpec workflow ⚠️

**Every behavioural change to this repository must go through OpenSpec.** This
is a hard rule for this hub, not a courtesy: the plugin's semantics are only
meaningful against the core's delegation contract, and the two sides evolve as
a coordinated triple. Bypassing the workflow or committing behaviour without a
spec first would make future contributions unverifiable.

### The workflow

```
new ──► propose ──► apply ──► sync ──► archive
 │         │           │         │        │
 │         │           │         │        └─► openspec archive <change>
 │         │           │         └─► spec delta merged into openspec/specs/
 │         │           └─► implementation + tests
 │         └─► delta spec + proposal + design + tasks
 └─► openspec new <change>  (creates openspec/changes/<change>/)
```

For each change you will write, in `openspec/changes/<change>/`:

- `proposal.md` — `## Why`, `## What Changes` (plain bullets),
  `## Capabilities` (`### New Capabilities` / `### Modified Capabilities`),
  `## Impact` (files, `vtherm_api` version, core compatibility, migration).
- `design.md` — decisions **`D1`, `D2`, …** with rationale and trade-offs.
- `specs/<capability>/spec.md` — the delta (see the format below).
- `tasks.md` — checklists (`- [ ]`), grouped by area.

### Writing a valid delta

This is the part the validator is strict about. Get it right from the start:

- **Header:** `# <capability> Specification`; then `## Purpose` (when adding
  to the capability for the first time, or restating it) and `## Requirements`.
- For a **new** requirement: an `## ADDED Requirements` section; for a change
  to an existing one: an `## MODIFIED Requirements` section — and the
  *entire* requirement is written, not just the diff.
  A single delta document may have **both** sections, and they are applied to
  the main spec as one transactional merge.
- **Requirement headings** are `### Requirement: <short name>` and the body
  must use **normative language** — `must`, `shall`, `must not` — with the
  *why* included in the requirement body.
- **Scenarios** are `#### Scenario: <name>` (exactly four hashes), each with a
  `WHEN … THEN …` (and optionally `AND …`) body. **At least one** scenario per
  requirement, and every scenario must stay coherent with the requirement body
  (the validator checks this in `--strict`).
- **Descriptions ≤ 500 characters.** Long paragraphs in a requirement body will
  make `openspec validate <change> --strict` fail.
- Do **not** restate the delta in `design.md` bullet form and then *again* in
  the spec — the spec is the source of truth, the design is the rationale.

### The commands (always via `rtk`)

```bash
rtk openspec new <change>                 # scaffold openspec/changes/<change>/
rtk openspec status --change <name> --json
rtk openspec validate --all --strict      # the gate: 0 failures expected
rtk openspec instructions specs --change <name> --json
rtk openspec instructions archive --change <name> --json
rtk openspec archive <change>             # merge delta → specs/ + move to archive/
```

**The gate is `rtk openspec validate --all --strict` and it must end with
`X/0` (X passing, 0 failing) before a PR is merged.** A known trap: a stale
`openspec/changes/<name>/` folder that contains only a (duplicate) `tasks.md`
with no `proposal.md` will make the validator report that change even though
it was already archived — if you see a "ghost" change in the validation output,
`diff` its `tasks.md` against `openspec/changes/archive/<date>-<name>/tasks.md`
and **delete the leftover** (it is a duplicate of the archived copy, not a
live change).

**Do not edit `openspec/specs/` directly.** The main spec is only ever the
result of an archived change; editing it by hand desynchronises the history.
If a spec is wrong, file a change with a MODIFIED requirement that fixes it.

### Example: a past change

`2026-11-25-vtherm-auto-start-stop-personnalise` shows the full shape of a
feature change: proposal, six design decisions (D1–D6), a delta with 10
ADDED requirements and 2 MODIFIED requirements, and 6 task groups. It is
archived, so its delta has been merged into
`openspec/specs/auto-start-stop-plugin/spec.md`. Read it before writing your
first proposal.

## 4. Design principles

The invariants (I1–I9) and decision list (D1–D16) of the original change are
the reference; they remain normative. The ones that most often bite:

1. **Pure detection.** `algorithm.py` has **no Home Assistant import**. The
   detector never talks to a thermostat object: it receives an immutable
   snapshot (a frozen dataclass) and produces a decision. Any HA-specific
   behaviour (entities, config entries, refresh) lives outside this module.
   *Corollary:* the algorithm is trivially unit-testable — see the test rules
   in §5.
2. **No scheduled refresh.** When the preset or target changes, the manager
   (a) resets the algorithm, (b) **synchronously** calls
   `async_request_state_refresh()` on the runtime interface and rebuilds the
   snapshot — it must *not* schedule a callback, `schedule_update_ha`, or a
   state-subscription callback. This is why D16 exists and why the core is
   the only side allowed to schedule anything.
3. **Persistence is by design.** The accumulated error, the level and the
   per-thermostat state (`_last_state`) survive reloads; the manager
   reconstructs `_last_state` and `_last_request_state` from the
   `InterfaceThermostatRuntime` and the persisted `has_accumulated_error`
   snapshot on init. `has_accumulated_error` is *read* on reload, never
   written by the plugin after init.
4. **The `none` legacy is normalised, not removed.** Any stored `none`
   value transparently resolves to the default level; no migration of stored
   state is ever required because `none` was never a stop mode.
5. **Eligibility is a single source of truth.** `factory.supports()` and the
   config-flow selector share the same rule
   (`over_climate and not has_valve_regulation` + legacy-entity offer). If
   you change one, you change both, or you change the capability's
   specification first (and the tests).
6. **Valve-regulated exclusion is absolute.** It is a *normative* scope
   decision (D14) inherited from the core, *not* a gap to be "fixed" as a
   side-effect. Lift it only through a spec change that says so.

## 5. Coding & testing rules

**Runtime** — Home Assistant ≥ 2026.10; `vtherm_api >= 0.13.1` is declared in
`manifest.json` and pinned in `requirements_test.txt`. **Never** import the
core as a Python package here; the only import path is `vtherm_api`.

**Algorithm** — the detector must be safe across time gaps, mode changes
(`off` short-circuits), preset/target changes (full reset) and sign changes
(halve). The constants `CYCLE_SEC`, `MIN_CYCLE_RATIO`, `TEMP_HYSTERESIS` are
normative; changing them is a behavioural change → OpenSpec change first.

**Testing**

```bash
python -m pytest tests/                # the full suite (pure, no HA needed)
```

- Tests are **pure** (no `pytest-homeassistant-custom-component`, no Home
  Assistant fixtures): `algorithm.py`, `models.py` and `registry.py` are
  tested as plain Python. `manager.py` is tested with *fake* runtime
  interfaces (a few dozen lines, see `tests/test_manager.py`).
- New behaviour → new test in the matching `tests/test_<module>.py`. Name
  tests after the requirement/scenario they encode when practical
  (e.g. `test_none_level_normalised_to_slow`).
- `tests/` must stay runnable **without a Home Assistant installation**; the
  integration's own `setup` is not exercised here.

**Lint / style** — match the surrounding code (no heavy formatter config in
the repo; keep imports at the top of the module, `from __future__ import
annotations` in new modules, frozen/slots dataclasses for new state models).

## 6. Adding documentation

- **User / installer docs** → `README.md` (English) + `README-fr.md`
  (French). Keep both files in sync; the header nav must cross-link the pair.
- **Contributor docs** → this file and its French twin. Any change to the
  OpenSpec workflow described here must match what `openspec/changes/`
  actually uses.
- **Language:** extensionless file = English (default); `-fr` suffix =
  French. Do not add a third language unless the repo gains one.
- **Never** copy the OpenSpec spec's `Requirement`/`Scenario` bodies verbatim
  into the README: the README explains *what the user sees*; the spec
  defines *what the system must do*.
