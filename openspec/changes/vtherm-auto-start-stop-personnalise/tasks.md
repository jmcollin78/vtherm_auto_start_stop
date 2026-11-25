# Tasks — vtherm-auto-start-stop-personnalise

## Implémentation

### Constantes et modèle
- [x] `const.py` : ajouter `LEVEL_PERSONNALISE` et les constantes `CONF_DT_MIN` / `CONF_ERROR_THRESHOLD` à `TYPE_LEVEL`.
- [x] `const.py` : retirer `LEVEL_NONE` de `LEVELS` et de `TYPE_LEVEL`. La constante de valeur historique `LEVEL_NONE` reste définie (valeur `auto_start_stop_none`) car des entries existantes peuvent la porter ; elle n'est plus une option du sélecteur.
- [x] `models.py` : vérifier que `normalize_level("auto_start_stop_none")` retourne `DEFAULT_LEVEL` (SLOW) via le fallback existant — aucun changement de code attendu, ajout d'un test dédié.

### Algorithme
- [x] `algorithm.py` : ajouter `LevelParams` `dt_min` et `error_threshold` (déjà présentes).
- [x] `algorithm.py` : étendre `AutoStartStopDetectionAlgorithm` avec une méthode `set_params(level: TYPE_LEVEL, config: dict[str, Any])` qui remplace `set_level` : elle appelle `resolve_params(level, config)` et fait le reset si le niveau *ou* la paire `LevelParams` a changé.
- [x] `algorithm.py` : remplacer `resolve_params(level)` par `resolve_params(level, config)` ; la branche `personnalise` lit `config`, avec fallback sur les valeurs du niveau SLOW.

### Retrait du niveau Aucun
- [x] `algorithm.py` : retirer les entrées `LEVEL_NONE` des tables `DT_MIN` et `ERROR_THRESHOLD` (la valeur inconnue passe par le fallback SLOW de `resolve_params`).
- [x] `algorithm.py` : dans `__init__`, remplacer l'initialisation `self._level = LEVEL_NONE` par `self._level = DEFAULT_LEVEL` pour cohérence.
- [x] `translations/fr.json` et `en.json` : retirer le libellé du niveau « Aucun » / « None ».
- [x] `tests/test_vocabulary.py` : adapter la liste attendue de `LEVELS` (plus de `auto_start_stop_none`).
- [x] `tests/test_models.py` : adapter les cases de `normalize_level` qui référencent `LEVEL_NONE` ; ajouter un case « `auto_start_stop_none` résout à SLOW ».
- [x] `tests/test_algorithm.py` : retirer les cases de `resolve_params` qui attendent les paires `LEVEL_NONE` (0/0) ; ajouter un case de fallback sur cette valeur.
- [x] `tests/test_manager.py` : adapter les scenarios qui créent une entry en `LEVEL_NONE` (par ex. ligne 426) — soit le niveau SLOW + interrupteur off, soit conserver `LEVEL_NONE` pour vérifier expressément le fondu.

### Manager
- [x] `manager.py` : dans `post_init`, passer `effective_config` à `algorithm.set_params(...)` au lieu de `algorithm.set_level(...)`. Mettre à jour `__init__` : construire l'algorithme avec les valeurs par défaut du plugin (SLOW).

### Config flow
- [x] `config_flow.py` : `_options_schema` accepte `defaults` et insère sélecteur `NumberSelector` si `defaults[CONF_LEVEL] == LEVEL_PERSONNALISE`, avec `NumberSelectorConfig(min=5, max=120, unit_of_measurement="min")` pour `dt_min` et `NumberSelectorConfig(min=1, max=50, step=0.5)` pour `error_threshold`.
- [x] `config_flow.py` : dans le traitement de submit (config et options flow), si `new_level == LEVEL_PERSONNALISE` et que le champ n'est pas dans `user_input`, injecter la valeur du niveau précédent (via `DT_MIN` / `ERROR_THRESHOLD`), sinon `DEFAULT_DT_MIN` / `DEFAULT_ERROR_THRESHOLD`.
- [x] `config_flow.py` : valider les bornes au submit (l'intégration HA le fait déjà pour `NumberSelector`, mais ajouter une garde défensive si on veut un message d'erreur spécifique).

### Translations
- [x] `strings.json` et `translations/fr.json` : `auto_start_stop_personnalise` (libellé du niveau), `auto_start_stop_dt_min` / `auto_start_stop_error_threshold` (libellés des champs), plus les libellés associés.
- [x] `translations/en.json` : idem en anglais.

## Tests

### Unitaires
- [x] `test_algorithm.py` : ajouter un test de `set_params("personnalise", {"dt_min": 45, "error_threshold": 25})` qui vérifie `dt_min == 45` et `error_threshold == 25`.
- [x] `test_algorithm.py` : ajouter un test de fallback : `set_params("personnalise", {})` → valeurs du niveau SLOW ; `set_params("unknown", {"dt_min": 45})` → fallback SLOW sur les deux.
- [x] `test_algorithm.py` : vérifier que le reset de l'accumulation se produit quand la paire `(level, LevelParams)` change (pas seulement le level).
- [x] `test_models.py` : ajouter des cas de cascade avec clés custom : global avec `dt_min=60`, dedicated avec `dt_min=20` → le dédiée gagne pour son thermostat, le global s'applique aux autres. Ajouter aussi un cas où le level des clé custom est absent (fallback).
- [x] `test_setup.py` : ajouter un scénario complet : config entry dédié avec level `personnalise` et `dt_min=45` → la manager expose `auto_start_stop_dtmin` = 45.

### Config flow
- [x] `test_config_flow.py` : ajouter un test du pré-remplissage : level `slow` (30/10) → au submit `level: personnalise`, l'entry résultante contient `dt_min: 30` et `error_threshold: 10`.
- [x] `test_config_flow.py` : ajouter un test que les clés custom restent dans `entry.options` après un passage `personnalise → medium → personnalise`.
- [x] `test_config_flow.py` : ajouter un test de validation : `dt_min: 3` et `dt_min: 200` sont refusés/clamped, `error_threshold: 0.5` et `60` idem.

### Intégration / compatibilité
- [x] `test_entity_state.py` : ajouter un test : un thermostat en `personnalise` avec `dt_min=45`, `error_threshold=25` expose les attributs `auto_start_stop_level == "personnalise"`, `auto_start_stop_dtmin == 45`, `auto_start_stop_accumulated_error_threshold == 25`.
- [x] Vérifier que les attributs `auto_start_stop_dtmin` / `auto_start_stop_accumulated_error_threshold` conservent exactement le même nom pour les niveaux nommés (pas de régression).

## Documentation
- [x] `README.md` : ajouter une section « Niveaux » qui documente le niveau `personnalise` et ses bornes.
- [x] `README.md` : documenter le comportement du pré-remplissage au switch.
