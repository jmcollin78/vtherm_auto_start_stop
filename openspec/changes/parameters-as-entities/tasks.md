# Tasks

## 1. Dérivation du niveau et modèle de paramètres

- [ ] 1.1 Ajouter `derive_level(dt_min, error_threshold)` dans `models.py`, avec
  une tolérance explicite sur les flottants ; vérifier que
  `pytest tests/test_models.py -k derive` passe pour les quatre couples nommés,
  une paire arbitraire et le cas `30.0` / `10.0`.
- [ ] 1.2 Ajouter `is_covered(entries, unique_id)` dans `models.py` et supprimer
  `_layers()`, `effective_config()` et `PARAMETER_OVERLAYS` ; vérifier que
  `pytest tests/test_models.py` passe avec les tests de couverture réécrits.
- [ ] 1.3 Étendre `initial_control_defaults()` aux trois paramètres de détection
  (niveau, durée, seuil) en conservant le contrat « ne jamais écraser un état
  sauvegardé » ; vérifier par un test que des entrées multiples ne produisent
  qu'une seule semence déterministe.

## 2. Pont d'état et registre à cinq entités

- [ ] 2.1 Ajouter `dt_min`, `error_threshold` et `level` à `ControlState` et
  étendre `async_apply_controls()` pour transmettre la paire au manager ;
  vérifier que `pytest tests/test_registry.py` passe.
- [ ] 2.2 Étendre `ensure_entities()`, `async_remove_controls()` et
  `async_reconcile_entities()` aux cinq plateformes via une table
  `_PLUGIN_SUFFIXES` à cinq entrées ; vérifier qu'un thermostat couvert produit
  exactement cinq entités et que la suppression les retire toutes.
- [ ] 2.3 Séparer `_HISTORICAL_PLATFORMS` (switch, select) de
  `_PLUGIN_SUFFIXES` dans `prepare_entity_ids()` ; vérifier par un test qu'aucune
  des trois nouvelles entités n'adopte un ID historique et que switch/select
  conservent la compatibilité existante.

## 3. Entités de paramètres

- [ ] 3.1 Créer `number.py` avec `AutoStartStopDtMinNumber` et
  `AutoStartStopErrorThresholdNumber` (`RestoreNumber`,
  `EntityCategory.CONFIG`, bornes 5–120 / 1–50) ; vérifier que
  `pytest tests/test_number.py` passe pour les bornes, la restauration et le
  refus hors bornes.
- [ ] 3.2 Refuser explicitement une valeur hors bornes dans
  `async_set_native_value()` avec une `ServiceValidationError` et une clé de
  traduction dédiée, en reprenant le patron du `select` ; vérifier qu'aucune
  entité ne devient indisponible à cause d'un refus.
- [ ] 3.3 Ajouter les libellés `number.*` dans `strings.json`,
  `translations/en.json` et `translations/fr.json`, plus la clé d'erreur de
  bornes ; vérifier que `pytest tests/test_vocabulary.py` passe et que
  `python -m script.translations develop --all` ne signale pas d'écart.
- [ ] 3.4 Enregistrer la plateforme `number` dans `PLATFORMS` et dans
  `async_setup_entry()` ; vérifier que `pytest tests/test_setup.py` passe et
  qu'un thermostat couvert expose bien ses deux entités de paramètres.

## 4. Niveau dérivé exposé par le select

- [ ] 4.1 Faire de `AutoStartStopStopModeSelect` la référence et créer
  `AutoStartStopLevelSelect` dont `current_option` est le niveau dérivé et dont
  `async_select_option()` appelle `manager.apply_level()` ; vérifier que
  `pytest tests/test_select.py` passe.
- [ ] 4.2 Refuser explicitement la sélection de `personnalise` quand la paire
  courante correspond déjà à un niveau nommé ; vérifier que le refus laisse
  l'option affichée inchangée et n'écrit aucun paramètre.
- [ ] 4.3 Publier les cinq entités dans `async_added_to_hass()` en écoutant le
  même signal `SIGNAL_MANAGER_UPDATED` ; vérifier qu'une sélection de niveau met
  à jour les trois entités en une seule notification.

## 5. Manager : opérations atomiques

- [ ] 5.1 Implémenter `apply_level(level)` dans le manager : écrire les deux
  paramètres dans `ControlState`, appeler `set_params()` une seule fois, publier
  une seule notification ; vérifier par un test que `_accumulated_error` n'est
  remis à zéro qu'une fois.
- [ ] 5.2 Implémenter `apply_parameters(dt_min, error_threshold)` : dériver le
  niveau via `derive_level()`, appeler `set_params()` une seule fois, publier une
  seule notification ; vérifier qu'écrire un seul paramètre ne réinitialise
  qu'une fois.
- [ ] 5.3 Remplacer `effective_config()` par `is_covered()` dans `post_init()`
  et semer les paramètres depuis l'entrée quand aucune valeur restaurée
  n'existe ; vérifier que `pytest tests/test_manager.py` passe.
- [ ] 5.4 Publier `ATTR_LEVEL` depuis le niveau mémorisé par le manager plutôt
  que depuis un champ stocké ; vérifier qu'un changement de paramètre se reflète
  dans les attributs du thermostat sans rechargement.

## 6. Réduction du flow et suppression du rechargement

- [ ] 6.1 Retirer les champs de paramètres de `_options_schema()` et conserver
  uniquement des semences étiquetées comme initialisation seule ; vérifier que
  `pytest tests/test_config_flow.py` passe avec les tests réécrits.
- [ ] 6.2 Supprimer `_async_update_options()` et `_reload_thermostats()` de
  `__init__.py` et les remplacer par une re-résolution des managers ; vérifier
  par un test qu'aucune entrée Versatile Thermostat n'est rechargée lors d'une
  modification d'entrée ni d'une écriture d'entité.
- [ ] 6.3 Mettre à jour `README.md` et `README-fr.md` : les paramètres se règlent
  sur les entités, le flow ne configure que la couverture et les semences ;
  vérifier que les liens et les noms d'entités cités existent dans les
  traductions.

## 7. Vérification d'intégration

- [ ] 7.1 Ajouter un test de bout en bout qui couvre le semis initial, une
  écriture d'entité, une sélection de niveau et un redémarrage ; vérifier qu'il
  passe avec `pytest tests/`.
- [ ] 7.2 Vérifier qu'aucun scénario des specs du delta n'est sans test ou
  vérification manuelle documentée, et que `openspec validate
  "parameters-as-entities" --strict` passe.

## Workflow follow-up

- Archiver le change après revue.
- Traiter ensuite le change `dashboard-config-card`, séparément.
