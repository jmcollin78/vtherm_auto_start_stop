# Proposal

> **Statut : en réserve.** Ce change capture les décisions déjà prises et les
> questions encore ouvertes sur la carte de configuration du dashboard. Il n'est
> pas destiné à être implémenté avant que `parameters-as-entities` soit archivé.
> Ses artefacts `specs/`, `design.md` et `tasks.md` seront produits quand le
> sujet sera ouvert ; tant qu'ils manquent, `openspec validate` le signale comme
> incomplet, ce qui est voulu.

## Why

`vtherm_dashboard` embarque une carte native `core_auto_start_stop` qui lit les
attributs `auto_start_stop_manager.*` publiés par le thermostat. Une fois la
décision déléguée au plugin, cette carte devient inutilisable pour deux raisons
indépendantes :

- sa visibilité exige `use_auto_start_stop_feature === true`, or la migration du
  core force ce flag à `false` — l'onglet et le widget disparaissent exactement
  quand le plugin prend la main ;
- elle est en lecture seule : `overview-widgets/spec.md` interdit explicitement
  à un widget d'appeler un service Home Assistant, donc elle ne peut pas écrire
  les paramètres.

Il faut donc une contribution du plugin lui-même, qui affiche **et** modifie les
paramètres — désormais des entités depuis `parameters-as-entities`.

## What Changes

- Le plugin enregistre une contribution UI via
  `vtherm_api.register_ui_plugin(plugin_id, js_url, dashboard_version, *,
  requires, load_after, load_before)`, avec `requires: ["core"]`.
- L'`plugin_id` ne peut pas commencer par `core_` : ce préfixe est réservé aux
  contributions natives du dashboard.
- La carte affiche les cinq contrôles (`enable`, `stop_mode`, `level`, `dt_min`,
  `error_threshold`) et les trois attributs non exposés en entité
  (`auto_start_stop_accumulated_error`,
  `auto_start_stop_accumulated_error_threshold`,
  `auto_start_stop_last_switch_date`).
- La carte écrit par `hass.callService` sur les entités du thermostat ciblé,
  résolues par `getEntryEntities(hass, entryId)`.
- La contribution native `core_auto_start_stop` devient legacy : soit le plugin
  la retire (`remove:`), soit le dashboard cesse de l'enregistrer quand le
  plugin est actif.

## Questions ouvertes

Ces trois points doivent être tranchés avant d'écrire `specs/` et `design.md`.

### A. Hook de contribution

- `tab_page` : conforme aux specs (une page d'onglet peut appeler des services),
  mais c'est un onglet séparé, pas une section dans la fiche du thermostat.
- `thermostat_config` : s'intègre là où l'utilisateur cherche le réglage, mais
  `ui-plugin-sdk/spec.md` interdit à un composant de configuration d'écrire la
  configuration lui-même — il devrait passer par un draft et
  `vtherm_dashboard/save_config`, qui écrit dans l'entrée du **thermostat**,
  alors que les paramètres vivent dans des entités du **plugin**.

Trancher A revient à décider si la carte est un onglet ou une section, donc si
l'une des deux specs doit être amendée.

### B. Dépendance de manifeste

- `dependencies: ["vtherm_dashboard", "http"]` : chargement garanti, mais le
  plugin refuse de démarrer sans le dashboard.
- `after_dependencies: ["vtherm_dashboard"]` : le plugin reste autonome, la carte
  n'est enregistrée que si le dashboard est présent. **Recommandé.**

### C. Retrait de la carte native legacy

- Immédiat, côté plugin : `remove:` les deux contributions natives
  (`core_auto_start_stop` et son widget). Fonctionne sans toucher au dashboard,
  mais reste un contournement — la contribution native serait réintroduite par
  toute réinstallation du dashboard.
- Durable, côté dashboard : ne pas enregistrer `core_auto_start_stop` dans
  `NATIVE_PLUGIN_ORDER` quand `get_ui_plugins()` signale le plugin actif.
  Nécessite une évolution de `vtherm_dashboard`, donc l'accord de son auteur.

## Impact

**Dépôt `vtherm_auto_start_stop`** — `manifest.json` (dépendances), un nouveau
`www/` avec la carte compilée, l'enregistrement au setup, `strings.json` et les
traductions.

**Dépôt `vtherm_dashboard`** — retrait de `core_auto_start_stop` de
`NATIVE_PLUGIN_ORDER` (option durable de C). Aucune écriture dans ce dépôt sans
accord de son auteur.

**Spécifications** — selon l'arbitrage de A, soit aucune spec ne bouge
(`tab_page`), soit `ui-plugin-sdk` doit être amendée (`thermostat_config`).
`overview-widgets` reste intacte dans les deux cas tant que la carte est une page
et non un widget.

**Dépendances** — `@vtherm/dashboard-sdk`, Node ≥ 24 et un build Vite vers
`custom_components/vtherm_auto_start_stop/www/`.

**Prérequis** — `parameters-as-entities` doit être archivé : la carte écrit sur
des entités qui n'existent pas encore.
