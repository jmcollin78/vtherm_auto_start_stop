# Design

## Context

Voir `proposal.md` — Why pour la motivation.

État actuel, tel qu'il contraint la conception :

- `models.py` résout la configuration en trois couches (`default_config`,
  instance globale, instance dédiée) via `effective_config()`. Cette fonction est
  aussi la **porte de couverture** : elle retourne `None` quand aucune instance
  n'existe, et `manager.post_init()` s'en sert pour décider de s'attacher.
- `manager.post_init()` appelle `algorithm.set_params(level, config)` avec la
  configuration fusionnée, puis `ensure_entities()`.
- `registry.py` connaît exactement **deux** plateformes via `_PLUGIN_SUFFIXES`
  (switch et select), et `ControlState` porte deux champs (`enabled`,
  `stop_mode`). `async_apply_controls()` sert de pont entre l'état restauré des
  entités et les managers reconstruits.
- `entity.AutoStartStopEntity` est une base `RestoreEntity` avec
  `ControlRestoreData` (versionné), `_valid_value()` et une restauration en
  cascade : état sauvegardé → entrée dédiée → `last_state` → défauts
  d'initialisation.
- `algorithm.AutoStartStopDetectionAlgorithm.set_params()` remet
  `_accumulated_error` à zéro **quand le niveau ou les paramètres changent**.
- `__init__._async_update_options()` déclenche `_reload_thermostats()`, qui
  appelle `async_reload` sur chaque entrée Versatile Thermostat.

Deux contraintes dures du modèle cible :

- `available = False` est interdit comme mécanisme de refus : Home Assistant
  filtre silencieusement les services ciblant une entité indisponible.
- Les cartes lisent `auto_start_stop_manager.auto_start_stop_level` ; l'attribut
  doit continuer d'exister.

## Goals / Non-Goals

**Goals:**

- Faire des trois paramètres des entités, sans changer le contrat de délégation
  ni les attributs publiés.
- Garantir qu'une écriture de paramètre ne recharge aucun thermostat.
- Garantir qu'un changement de niveau ne réinitialise l'accumulation qu'une fois.
- Sérialiser la migration d'une installation existante sans perte de réglage.

**Non-Goals:**

- La carte du dashboard et son hook de contribution
  (change `dashboard-config-card`).
- Le retrait de `core_auto_start_stop` des plugins natifs du dashboard.
- Une entité « niveau » qui serait une source de vérité : elle reste dérivée.
- Le support d'un niveau `none` ou d'un niveau personnalisé nommé librement.

## Decisions

### D1 — Le paramètre vit dans l'entité ; l'entrée ne sème qu'une fois

`ControlState` (le pont mémoire déjà utilisé pour enable et stop_mode) gagne
trois champs : `dt_min`, `error_threshold`, `level`. Les entités `number` et
`select` restaurent leur valeur comme les entités existantes le font, et
 publient leur valeur au manager via `async_apply_controls()`.

L'entrée de configuration ne fournit plus qu'une **semence** : ses clés
`auto_start_stop_level`, `auto_start_stop_dtmin` et
`auto_start_stop_error_threshold` sont lues uniquement quand aucune valeur
restaurée n'existe. C'est exactement le contrat déjà en place pour
`CONF_ENABLED` et `CONF_STOP_MODE`, via `initial_control_defaults()`. On étend
cette fonction plutôt que d'inventer un second mécanisme.

*Alternative écartée* : garder la cascade pour les paramètres et n'ajouter que
des entités en façade en écriture. Rejetée : deux sources de vérité, et la
relecture au démarrage devrait arbitrer entre une entrée modifiée à la main et
une entité restaurée, sans règle défendable.

### D2 — Le niveau est dérivé, avec une table inverse explicite

`algorithm.py` porte déjà `DT_MIN` et `ERROR_THRESHOLD`, indexées par niveau.
La table est **injective** : aucun couple de valeurs n'appartient à deux
niveaux. On ajoute donc une fonction pure, dans `models.py` :

```
derive_level(dt_min, error_threshold) -> str
```

Elle parcourt les niveaux nommés dans un ordre stable et retourne le premier
dont le couple correspond ; sinon `LEVEL_PERSONNALISE`. La comparaison tolère
les flottants (les entités `number` peuvent rendre `30.0`), avec une tolérance
serrée et documentée.

Placée dans `models.py` et non `algorithm.py` : `algorithm.py` reste la
traduction « niveau → paramètres », `models.py` la traduction inverse
« paramètres → niveau ». Les deux tables restent dans `algorithm.py`, seule
source des valeurs.

*Alternative écartée* : stocker le niveau dans un `select` et le traiter comme
la vérité, en réécrivant les `number` à chaque sélection. Rejetée : un
utilisateur qui écrit `dt_min = 20` obtiendrait un niveau incohérent avec ses
paramètres, ou verrait sa valeur écrasée.

### D3 — `apply_level()` est atomique et vit dans le manager

Sélectionner un niveau nommé doit écrire deux entités. Fait naïvement, chaque
écriture déclenche `set_params()` et donc une remise à zéro de
`_accumulated_error`, et l'état intermédiaire (un paramètre neuf, l'autre ancien)
est visible.

Le manager expose donc une opération unique :

```
apply_level(level)   # écrit dt_min + threshold, puis set_params() une fois
```

Elle écrit `ControlState` (les deux paramètres et le niveau), puis appelle
`set_params()` **une seule fois** avec le couple final, puis publie une seule
notification `SIGNAL_MANAGER_UPDATED`. Les entités écoutent ce signal et
republient leur état : elles ne s'écrivent jamais entre elles.

Les entités `number` passent par un chemin symétrique,
`apply_parameters(dt_min, error_threshold)`, qui recalcule le niveau dérivé et
appelle `set_params()` une fois.

*Alternative écartée* : laisser `select.async_select_option()` écrire les deux
entités `number` par `async_set_value`. Rejetée : deux cycles de restauration,
deux `set_params()`, et un couplage entité → entité que le modèle actuel évite
déjà (les entités ne se parlent que par le manager et le dispatcher).

### D4 — La porte de couverture se sépare de la résolution

`effective_config()` disparaît, mais son rôle de porte reste nécessaire : sans
lui, `post_init()` ne saurait pas s'il doit s'attacher. On introduit une
fonction dédiée, `is_covered(entries, unique_id) -> bool`, qui répond uniquement
« une instance globale ou dédiée existe-t-elle pour ce thermostat ». Elle
remplace l'appel `if config is None` dans `post_init()`.

`entry_config()`, `default_config()`, `initial_control_defaults()`,
`dedicated_entries()`, `has_dedicated_instance()`, `normalize_level()`,
`normalize_stop_mode()` et `legacy_level()` restent. `_layers()` et
`PARAMETER_OVERLAYS` disparaissent avec `effective_config()`.

### D5 — Deux entités `number`, avec un refus explicite et jamais d'indisponibilité

`number.py` fournit `AutoStartStopDtMinNumber` et
`AutoStartStopErrorThresholdNumber`, sur `RestoreNumber` + `AutoStartStopEntity`,
`EntityCategory.CONFIG`.

- `native_min_value = 5`, `native_max_value = 120`, `native_step = 1`,
  `native_unit_of_measurement = UnitOfTime.MINUTES` pour `dt_min` ;
- `native_min_value = 1`, `native_max_value = 50`, `native_step = 0.5` pour le
  seuil.

`native_min_value`/`native_max_value` font que Home Assistant refuse déjà une
valeur hors bornes. Le plugin ajoute une garde explicite dans
`async_set_native_value()` qui lève une `ServiceValidationError` avec une clé de
traduction dédiée, sur le modèle exact de
`invalid_auto_start_stop_option` déjà utilisé par le `select` : c'est le patron
établi du dépôt pour refuser proprement.

`available` **n'est pas** surchargé pour refuser : la propriété héritée de
`AutoStartStopEntity` reste `manager is not None and controls_ready and ...`,
donc un paramètre est disponible dès que le thermostat est couvert, y compris
désactivé.

### D6 — Le `select` de niveau devient un préréglage

`AutoStartStopLevelSelect` remplace le stockage : `options` est la liste des
niveaux nommés plus `personnalise`, `current_option` est le niveau **dérivé**,
et `async_select_option()` appelle `manager.apply_level()`. Sélectionner
`personnalise` n'écrit rien : c'est l'état résultant d'une paire arbitraire. Si
l'utilisateur le sélectionne alors que la paire courante correspond à un niveau
nommé, l'option est refusée explicitement — sinon la sélection serait un
no-op silencieux qui laisserait l'UI afficher autre chose que ce qui vient d'être
choisi.

### D7 — Plus de rechargement de thermostat

`__init__._async_update_options()` et `_reload_thermostats()` sont supprimés.
Une modification d'entrée ne change plus que la couverture et les semences, donc
elle se contente de re-résoudre les managers (`ensure_all_entities()` +
`async_reconcile_entities()`, déjà en place) sans toucher aux entrées Versatile
Thermostat. Une écriture d'entité ne touche même pas l'entrée.

### D8 — Le `config_flow` se réduit à la couverture

`_options_schema()` perd les champs de paramètres ; il garde les valeurs de
semence, explicitement étiquetées comme initialisation seule (le libellé existe
déjà pour enable et stop_mode). La sélection du thermostat, la vérification
d'éligibilité et `legacy_level()` sont inchangées.

### D9 — Le registre passe de deux à cinq entités

`_PLUGIN_SUFFIXES` devient une table `plateforme → suffixe` de cinq entrées, et
`ensure_entities()` crée les cinq. `prepare_entity_ids()` reste **inchangé dans
son principe** : il n'adopte des IDs historiques que pour switch et select, car
les trois nouvelles entités n'ont pas d'antécédent côté core. On garde donc deux
tables distinctes — `_HISTORICAL_PLATFORMS` (switch, select) et
`_PLUGIN_SUFFIXES` (les cinq) — pour ne pas transformer la compatibilité
historique en adoption silencieuse d'IDs arbitraires.

`async_remove_controls()` et `async_reconcile_entities()` itèrent sur
`_PLUGIN_SUFFIXES`, donc les cinq entités sont supprimées et déplacées ensemble.

### D10 — L'attribut de niveau reste dérivé et publié

`add_custom_attributes()` publie `ATTR_LEVEL` depuis
`derive_level(dt_min, threshold)` et non depuis un champ stocké. Le manager
conserve un cache du niveau courant, recalculé à chaque `apply_level()` /
`apply_parameters()`, pour ne pas dériver à chaque lecture d'attribut.

## Risks / Trade-offs

- **Perte des valeurs personnalisées au changement de niveau** → Assume et
  documenté dans la spec (`Leaving personnalise discards the custom values`).
  Mitigation : aucune, c'est le prix de la suppression de l'état caché ; la
  migration ne prétend pas restaurer d'anciennes valeurs personnalisées.
- **Une entrée modifiée à la main ne change plus les paramètres en service** →
  C'est le comportement voulu, mais il surprendra. Mitigation : libellés de
  semence explicites dans le flow, et document utilisateur mis à jour.
- **Écriture partielle si `apply_level()` échoue entre les deux entités** →
  Mitigation : l'écriture se fait d'abord dans `ControlState` (mémoire), puis
  dans les entités ; un échec de publication ne laisse pas le manager dans un
  état intermédiaire, et `apply_parameters()` est rejouable.
- **Deux entités pour un seul concept** → Un utilisateur peut régler une paire
  absurde (`dt_min = 5`, seuil `50`). Mitigation : c'est précisément ce que
  `personnalise` autorise aujourd'hui ; les bornes restent celles de la spec.
- **Dérivation flottante** → `30.0` vs `30` ou un arrondi de `number` pourrait
  empêcher la reconnaissance d'un niveau nommé. Mitigation : tolérance explicite
  et test dédié sur les pas de `0.5`.
- **Compatibilité des ID historiques étendue par erreur** → Mitigation : les
  deux tables séparées de D9, et un test qui vérifie qu'aucune des trois
  nouvelles entités n'adopte d'ID hérité.

## Migration Plan

1. Les entrées existantes restent valides : aucune clé n'est supprimée ni
   renommée, elles perdent seulement leur effet en service.
2. Au premier démarrage après mise à jour, pour chaque thermostat couvert :
   - `level` → couple de la table → semence des deux `number` ;
   - `dtmin` / `error_threshold` d'une entrée dédiée → semence directe.
3. Une valeur restaurée gagne toujours sur la semence.
4. Aucune migration destructive, aucun `async_migrate_entry`. Une entrée qui
   stocke encore `auto_start_stop_none` se résout en paramètres par défaut, sans
   réécriture.
5. Rollback : revenir au commit précédent restaure la cascade, les entrées
   n'ayant pas été modifiées. Les états d'entités des cinq contrôles restent
   dans le registre de restauration et sont ignorés par la version antérieure
   pour les trois nouvelles.

## Open Questions

Aucune question bloquante. Le choix de la carte (hook `tab_page` vs
`thermostat_config`) et le retrait de `core_auto_start_stop` sont traités dans
`dashboard-config-card` et n'affectent ni les specs ni le découpage des tâches
de ce change.
