# Spec Delta

## ADDED Requirements

### Requirement: Detection parameters as entities

Each covered thermostat SHALL expose its detection parameters as writable Home Assistant entities rather than configuration-entry values: a minimum duration, an error threshold, and a level preset. Their states SHALL persist across reloads and restarts independently of any configuration entry.

#### Scenario: A covered thermostat exposes three parameter entities

- **WHEN** a thermostat is covered by the plugin
- **THEN** it has one minimum-duration entity, one error-threshold entity and one level-preset entity, in addition to its enable switch and stop-mode select
- **AND** all of them attach to the thermostat's own device

#### Scenario: A parameter change takes effect without a reload

- **WHEN** a user writes a new value to a minimum-duration or error-threshold entity
- **THEN** the attached manager uses the new value from its next refresh
- **AND** no thermostat is reloaded and no configuration entry is written

#### Scenario: Parameter states survive a restart

- **WHEN** the integration restarts after a user changed a parameter entity
- **THEN** each entity restores the value the user set instead of the value seeded by the configuration entry

#### Scenario: An uncovered thermostat exposes no parameter entities

- **WHEN** neither the global nor a dedicated configuration covers a thermostat
- **THEN** no minimum-duration, error-threshold or level-preset entity is exposed for it

### Requirement: Level derived from the parameters

The level SHALL be a preset label derived from the two parameters, not a stored source of truth. It SHALL read as a named level when the pair equals that level's values, and as `personnalise` otherwise. Selecting a named level SHALL write both parameters as one coherent change.

#### Scenario: An unchanged pair reads as its named level

- **WHEN** the minimum duration and error threshold equal a named level's pair
- **THEN** the level preset reads as that named level

#### Scenario: An arbitrary pair reads as personnalise

- **WHEN** the minimum duration and error threshold do not equal any named level's pair
- **THEN** the level preset reads as `personnalise`

#### Scenario: Selecting a named level writes both parameters at once

- **WHEN** a user selects a named level
- **THEN** the minimum duration and error threshold are both set to that level's values
- **AND** the level preset reads as that level
- **AND** all five controls reflect the change together, with no intermediate state visible

#### Scenario: Writing one parameter reclassifies the level

- **WHEN** a user writes a single parameter that no longer matches the current named level
- **THEN** the level preset reads as `personnalise`
- **AND** all five controls reflect the change together, with no intermediate state visible

#### Scenario: Leaving personnalise discards the custom values

- **WHEN** the level preset reads as `personnalise` and the user selects a named level
- **THEN** the custom minimum duration and error threshold are replaced by that level's values
- **AND** the previous custom values are not retained anywhere

### Requirement: Accumulated deviation stays bounded by the threshold

The accumulated deviation SHALL remain bounded to the current error threshold, in both directions. The bound SHALL be re-applied with the current threshold on every detection cycle, so lowering the threshold bounds an existing accumulation and raising it leaves the accumulation where it is. Nothing SHALL be scaled or reconstructed from the previous threshold.

#### Scenario: The accumulation never exceeds the current threshold

- **WHEN** a detection cycle runs with a given error threshold
- **THEN** the accumulated deviation is bounded to that threshold in magnitude
- **AND** it is not scaled to preserve a ratio with the previous threshold

#### Scenario: Raising the threshold does not inflate the accumulation

- **WHEN** the error threshold is raised above the current accumulated deviation
- **THEN** the accumulation keeps its current magnitude
- **AND** it is not stretched toward the new threshold

### Requirement: Parameter changes preserve the accumulated deviation

Writing a detection parameter SHALL NOT reset the accumulated deviation. The deviation measures an observed temperature gap; the parameters are reading criteria applied to it, so changing a criterion SHALL NOT discard the measurement. Only an explicit user change of the target or the preset SHALL clear the delay.

#### Scenario: A parameter write leaves the accumulation intact

- **WHEN** a user writes the minimum duration or the error threshold between two detection cycles
- **THEN** the accumulated deviation keeps the value it had before the write
- **AND** the detection decision at the next cycle uses it

#### Scenario: Tuning a threshold does not restart the observation

- **WHEN** a user adjusts a parameter several times in a row while a stop is being approached
- **THEN** each write leaves the accumulated deviation intact
- **AND** the approach is not restarted by any of them

#### Scenario: A new level applies to the existing observation

- **WHEN** a user selects a named level whose values differ from the current parameters
- **THEN** the new criteria apply to the deviation already accumulated
- **AND** the deviation is not cleared

#### Scenario: A faster level can detect a stop on the next cycle

- **WHEN** a thermostat sits at a slow level with its deviation saturated at that level's threshold, and the user selects a faster level
- **THEN** the accumulation stays saturated, because the faster level's threshold is below the current accumulation
- **AND** the faster level's minimum duration is measured against the time elapsed since the last decision, not restarted
- **AND** a stop may therefore be detected on that cycle, without waiting for a new accumulation period

#### Scenario: A slower level cannot detect a stop on the next cycle

- **WHEN** a thermostat sits at a fast level with its deviation saturated at that level's threshold, and the user selects a slower level
- **THEN** the accumulation is no longer saturated, because the slower level's threshold is above it
- **AND** no stop is detected on that cycle on account of the level change alone
- **AND** detection resumes only once the accumulation reaches the new threshold again

#### Scenario: An explicit target change still clears the delay

- **WHEN** the thermostat's target temperature or preset changes
- **THEN** the switch delay is cleared as before
- **AND** the accumulated deviation is still not reset

### Requirement: Configuration defaults initialize entities only

The global enable, stop-mode, level, minimum-duration and error-threshold values SHALL initialize the five control entities when they have no saved state. Later changes to those defaults SHALL NOT overwrite an existing entity state. Once initialized, a covered thermostat's detection parameters SHALL come from its own entities and SHALL NOT be inherited from a global or dedicated entry, which keeps a coverage role and a seed role only.

#### Scenario: New controls use current initialization defaults

- **WHEN** an eligible thermostat has no saved control states and is first covered by the global configuration
- **THEN** its switch, stop-mode select, level select and two parameter numbers start with the current initialization defaults, restricted to supported stop modes and known levels

#### Scenario: Changed defaults do not reset existing controls

- **WHEN** existing controls have saved states and the global defaults are changed
- **THEN** existing entity states are retained, including after reload and restart
- **AND** eligible thermostats added later without saved states use the new defaults

#### Scenario: Detection parameters are not inherited after initialization

- **WHEN** a global detection parameter is changed while a covered thermostat already has parameter entity states
- **THEN** the thermostat keeps its entity values
- **AND** neither its controls nor its parameter entities are reset from the entry

### Requirement: Parameter resolution from entities

The manager SHALL read the minimum duration and the error threshold from the thermostat's own entities and derive the level from that pair. The named-level table SHALL remain the single source of the pair written when a level is selected. An unknown level, or an unusable stored value, SHALL resolve to the default parameters without failing the refresh.

#### Scenario: A named level resolves to its table pair

- **WHEN** the level preset is one of the named levels
- **THEN** its minimum duration and error threshold are that level's table values
- **AND** the manager's algorithm uses exactly those values

#### Scenario: An arbitrary pair resolves to personnalise

- **WHEN** the two parameter entities hold a pair that matches no named level
- **THEN** the level preset reads `personnalise`
- **AND** the manager's algorithm uses the entity pair as-is

#### Scenario: A stale or unknown parameter does not fail the refresh

- **WHEN** a stored level or parameter value cannot be interpreted
- **THEN** the resolution step falls back to the default parameters (Slow: 30 / 10)
- **AND** the refresh cycle does not fail

## MODIFIED Requirements

### Requirement: Plugin entities

The plugin SHALL create exactly five controls for each eligible thermostat covered by a global or dedicated configuration: an enable switch, a stop-mode select, a level select and two parameter numbers, all on the thermostat's own device. A global configuration alone SHALL suffice. The stop-mode select SHALL offer off and supported fan_only/dry, never disabled or heat/cool/auto. The level select SHALL offer only the named levels and `personnalise`.

#### Scenario: Global configuration alone creates two controls per thermostat

- **WHEN** only the global configuration exists and several non-valve-regulated over_climate thermostats are present
- **THEN** every such thermostat has exactly one enable switch and one stop-mode select, plus one level select and two parameter numbers, five controls in total
- **AND** no dedicated configuration is required or automatically created

#### Scenario: Disabled initialization defaults do not suppress entities

- **WHEN** only the global configuration exists, its enable default is false and eligible thermostats have no saved states
- **THEN** every eligible thermostat has an off enable switch, a stop-mode select showing its supported initial stop mode, a level select and two parameter numbers
- **AND** their managers and attributes remain configured

#### Scenario: A dedicated instance has two controls

- **WHEN** an eligible thermostat has its own dedicated parameter instance, with or without a global instance
- **THEN** it has exactly one enable switch and one stop-mode select, never a second pair
- **AND** it has a single level select and a single pair of parameter numbers

#### Scenario: Options only contain compatible stop modes

- **WHEN** a thermostat supports off, heat and fan_only but not dry
- **THEN** the select options are off and fan_only in that order
- **AND** disabled, heat and dry are not offered

#### Scenario: The level select offers only named levels and personnalise

- **WHEN** the level select is displayed
- **THEN** its options are the named levels and `personnalise`
- **AND** no `none` option is offered

#### Scenario: Stop-mode options update once the accepted hvac modes settle

- **WHEN** a manager was registered before the underlying climate of an over_climate attached, so the select initially exposes only the fallback options
- **AND** the underlying later attaches and exposes more accepted hvac modes such as fan_only or dry
- **THEN** the plugin re-publishes the select state so it gains the newly supported stop modes
- **AND** the user does not need to restart or interact with the control to see the updated options

#### Scenario: Controls and stop modes are localized

- **WHEN** the controls are displayed with French or English translations
- **THEN** the switch, both selects, both numbers and supported stop-mode labels use the selected language

#### Scenario: An eligible thermostat is added after the global configuration

- **WHEN** another eligible thermostat is added while the global configuration exists
- **THEN** the plugin creates its own five controls without requiring a dedicated configuration

#### Scenario: Ineligible thermostats have no controls

- **WHEN** a thermostat is not over_climate or is valve-regulated
- **THEN** the plugin creates none of the five controls for it, regardless of the global defaults

#### Scenario: No configuration means no controls

- **WHEN** neither a global configuration nor a dedicated parameter configuration covers a thermostat
- **THEN** no plugin manager or plugin control is exposed for it

### Requirement: Personnalise level parameter bounds

The minimum-duration entity SHALL accept a range of 5 to 120 minutes and the error-threshold entity a range of 1 to 50. A value outside these bounds SHALL be refused with an explicit validation error, leaving the previous value and the accumulated deviation untouched.

#### Scenario: Out-of-range values are refused or clamped

- **WHEN** a user writes a minimum duration below 5 minutes or above 120 minutes
- **THEN** the write is refused with an explicit error and the entity keeps its previous value
- **AND** the same applies to an error threshold below 1 or above 50

#### Scenario: A refused value does not disturb detection

- **WHEN** an out-of-bounds write is refused
- **THEN** the accumulated deviation and the current level are unchanged

### Requirement: Controls survive parameter-configuration changes

Adding or removing a dedicated parameter configuration SHALL NOT duplicate, rename or reset an existing set of controls while a global configuration still covers the thermostat. Removing global coverage SHALL retain controls for thermostats still covered by dedicated parameter entries.

#### Scenario: A dedicated parameter entry is added

- **WHEN** a globally covered thermostat already has its controls and a dedicated parameter entry is added
- **THEN** the same entities retain their IDs and saved states

#### Scenario: A dedicated parameter entry is removed

- **WHEN** a dedicated parameter entry is removed while global coverage remains
- **THEN** the same controls retain their IDs and states
- **AND** their parameter values are unchanged, since they are no longer inherited from the entry

#### Scenario: The global configuration is removed

- **WHEN** the global configuration is removed
- **THEN** thermostats with dedicated parameter entries retain their controls and saved states
- **AND** thermostats without remaining coverage expose neither plugin manager nor plugin controls

### Requirement: Migration from the core configuration

When the plugin starts covering a thermostat, the level found in the thermostat entry or in the plugin entry SHALL seed the parameter entities once, and SHALL NOT overwrite a value already restored from an entity state.

#### Scenario: The core level is adopted

- **WHEN** a thermostat entry carries a legacy auto-start/stop level and the plugin starts covering it with no restored parameter state
- **THEN** the parameter entities are seeded from that level's table values

#### Scenario: A restored entity state wins over the seed

- **WHEN** a parameter entity restores a saved state
- **THEN** the configured seed value does not overwrite it

#### Scenario: The legacy level is not reused twice

- **WHEN** the plugin already covered the thermostat and its parameter entities have states
- **THEN** a subsequent configuration does not reset them from the legacy value

### Requirement: Published attributes and off-reason

The plugin SHALL publish the same auto-start/stop attribute section as the core feature and SHALL use the same off-reason vocabulary, so existing cards and summaries keep working. The published level SHALL be the derived preset, not a separately stored value.

#### Scenario: The attribute section is present

- **WHEN** a thermostat managed by the plugin exposes its custom attributes
- **THEN** the auto-start/stop section contains the detection flag, the level, the minimum duration, the accumulated deviation, its threshold, the last switch date, the stop mode and the enable state

#### Scenario: The published level follows the parameters

- **WHEN** the two parameter entities no longer match a named level's pair
- **THEN** the published level attribute reads `personnalise`

#### Scenario: The off-reason is unchanged

- **WHEN** the thermostat is stopped by the plugin
- **THEN** its off-reason is the auto-start/stop reason already used by the core feature

## REMOVED Requirements

### Requirement: Layered configuration resolution

**Reason**: Les paramètres de détection ne sont plus résolus en couches : ils vivent dans des entités par thermostat, et l'entrée ne porte plus que la couverture et les valeurs de semence. La cascade plugin → global → dédié n'a plus d'objet.

**Migration**: Les entrées existantes conservent leur rôle de couverture et leurs valeurs `level`, `dt_min` et `error_threshold` initialisent les nouvelles entités au premier démarrage. Un utilisateur qui réglait un paramètre via l'instance globale le règle désormais sur l'entité du thermostat concerné, ou par service.

### Requirement: Direct dedicated configuration flow

**Reason**: L'entrée ne configure plus de paramètres de détection. Le flow se réduit à la sélection du thermostat couvert et aux valeurs de semence.

**Migration**: La couverture et l'éligibilité sont inchangées. Les champs de paramètres quittent le formulaire ; les valeurs se règlent sur les entités du thermostat. Un utilisateur qui ouvrait le flow pour ajuster un seuil utilise maintenant l'entité correspondante.

### Requirement: Enable and stop-mode defaults initialize entities only

**Reason**: L'exigence survit dans son principe mais son dernier scénario affirme que des paramètres de détection globaux s'appliquent aux thermostats héritiers, ce qui n'est plus vrai. Elle est remplacée par « Configuration defaults initialize entities only », qui couvre les cinq contrôles au lieu de deux.

**Migration**: Aucune action. L'initialisation des entités sans état sauvegardé est identique ; seule la source des paramètres de détection change, de l'entrée vers les entités.

### Requirement: Phase-2 parameter readiness

**Reason**: La résolution lisait les paramètres depuis la configuration effective fusionnée. Elle les lit maintenant depuis les entités du thermostat, avec la table du niveau comme repli. Elle est remplacée par « Parameter resolution from entities ».

**Migration**: Aucune action. Les valeurs déjà présentes dans une entrée servent de semence et produisent la même résolution au premier démarrage.

### Requirement: Custom value persistence across level switches

**Reason**: Le niveau n'est plus un stockage : les valeurs personnalisées n'ont donc plus d'endroit où survivre à un changement de niveau. Les conserver exigerait de réintroduire un état caché, que ce change supprime délibérément.

**Migration**: Aucune. Passer d'un niveau `personnalise` à un niveau nommé remplace les valeurs personnalisées sans copie de sauvegarde. Un utilisateur qui veut retrouver ses valeurs les règle à nouveau sur les deux entités de paramètres.

### Requirement: Removal of the none level

**Reason**: Le vocabulaire n'est plus stocké dans une entrée : il est la liste des préréglages exposée par l'entité de niveau. La dérivation ne produit que les niveaux nommés ou `personnalise`, donc aucune valeur `none` ne peut réapparaître.

**Migration**: Une entrée qui stocke encore `none` est traitée comme une semence inconnue et se résout en paramètres par défaut, sans migration d'entrée.
