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
  C'est le comportement actuel, et c'est précisément ce que ce change supprime
  (voir D11).
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
- Garantir qu'une écriture de paramètre ne réinitialise pas l'accumulation, et
  qu'un changement de niveau reste une opération unique et cohérente.
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

### D3 — `apply_level()` est une écriture cohérente, sans effet de bord

Sélectionner un niveau nommé doit écrire deux entités. Fait naïvement, chaque
écriture déclencherait deux passages par le manager, et l'état intermédiaire (un
paramètre neuf, l'autre ancien) serait visible des entités.

Le manager expose donc une opération unique :

```
apply_level(level)   # écrit dt_min + threshold, puis publie une fois
```

Elle écrit `ControlState` (les deux paramètres et le niveau), met à jour les
paramètres de l'algorithme, puis publie **une seule** notification
`SIGNAL_MANAGER_UPDATED`. Les entités écoutent ce signal et republient leur
état : elles ne s'écrivent jamais entre elles.

Les entités `number` passent par un chemin symétrique,
`apply_parameters(dt_min, error_threshold)`, qui recalcule le niveau dérivé et
publie une seule fois.

D3 ne porte **plus** sur la réinitialisation de l'accumulation : elle n'a plus
lieu du tout (voir D11). L'atomicité ne sert donc plus qu'à garantir une vue
cohérente des cinq entités, pas à contenir un effet de bord.

*Alternative écartée* : laisser `select.async_select_option()` écrire les deux
entités `number` par `async_set_value`. Rejetée : deux cycles de restauration,
deux passages par le manager, et un couplage entité → entité que le modèle
actuel évite déjà (les entités ne se parlent que par le manager et le
dispatcher).

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

### D11 — Changer un paramètre ne réinitialise plus l'accumulation

`set_params()` remet aujourd'hui `_accumulated_error` à zéro dès que le niveau
ou le couple change. Ce comportement est supprimé : changer un paramètre ne
touche plus à l'intégrale.

Justification : `_accumulated_error` est l'intégrale de l'écart
`target - current` pondérée par le temps. Elle mesure une **observation
physique** du comportement du thermostat, pas un réglage. `dt_min` et le seuil
sont des **critères de lecture** appliqués à cette observation. Changer un
critère ne change pas ce qui s'est passé dans la pièce, donc jeter la mesure est
une perte d'information, pas une précaution.

Conséquences concrètes, toutes favorables :

- l'utilisateur peut tâtonner sur ses seuils sans repartir de zéro à chaque
  essai, ce qui est le geste naturel quand on cherche le bon réglage ;
- un `dt_min` réduit prend effet immédiatement sur une accumulation déjà
  constituée, au lieu d'imposer une attente complète du nouveau délai ;
- une écriture de paramètre devient une opération sans effet de bord : aucune
  remise à zéro à sérialiser, donc D3 n'a plus à protéger qu'une vue cohérente.

Effet conservé, et c'est une condition du modèle, pas un détail : le
**plafonnement**. `_accumulated_error` reste borné à `±error_threshold` à chaque
cycle, sans aucun redimensionnement (voir D12). C'est lui qui rend les deux sens
de changement de niveau asymétriques :

| Sens          | Intégrale | Ancien seuil | Nouveau seuil | Après plafonnement    | Stop immédiat ? |
| ------------- | --------- | ------------ | ------------- | --------------------- | --------------- |
| Lent → Rapide | 10        | 10 (saturée) | 2             | 2, donc au seuil      | **possible**    |
| Rapide → Lent | 2         | 2 (saturée)  | 10            | 2, donc sous le seuil | **non**         |

Ce qui reste réinitialisé, et pourquoi :

- `reset_switch_delay()` (délai anti-rebond après un changement de consigne ou
  de préréglage thermique) : c'est une décision *explicite* de l'utilisateur sur
  la consigne, pas un réglage de détection. Inchangé.
- `restore()` au redémarrage : inchangé, il restaure au contraire
  l'accumulation.

*Alternative écartée* : ne pas réinitialiser mais repartir d'une accumulation
mise à l'échelle du nouveau seuil (rapport `nouveau / ancien`). Rejetée : cette
mise à l'échelle rendrait le passage Rapide → Lent capable de déclencher un stop
immédiat, ce qui n'a aucun sens — l'utilisateur vient justement de demander une
réaction moins sensible. Voir D12.

*Alternative écartée* : conserver la réinitialisation et l'exposer comme une
option. Rejetée : deux comportements à tester, à documenter et à maintenir pour
un cas d'usage qui n'a pas été demandé.

**Corollaire voulu, dans un seul sens** — passer à un niveau plus **rapide** peut
déclencher la détection dès le cycle suivant ; passer à un niveau plus **lent**
ne le peut pas. Les deux scénarios de la spec sont symétriques et explicites :
`A faster level can detect a stop on the next cycle` et
`A slower level cannot detect a stop on the next cycle`.

Le mécanisme du sens rapide repose sur deux garde-fous qui se relâchent
ensemble :

1. `_accumulated_error` est déjà saturé à l'ancien seuil ; le nouveau seuil
   étant plus bas, il reste au-delà : la condition de seuil est satisfaite
   d'emblée ;
2. `_last_switch_date` n'est **pas** touché par `set_params()` (vérifié dans
   `algorithm.py`), donc `minutes_since_switch` continue d'être mesuré depuis la
   dernière décision réelle. Un `dt_min` plus court est donc immédiatement
   satisfait lui aussi.

Dans le sens inverse, aucun des deux ne se relâche : le seuil relevé n'est plus
atteint, et le `dt_min` allongé n'est pas satisfait. C'est exactement le
comportement attendu : choisir un niveau plus lent, c'est demander moins de
sensibilité, donc surtout pas un stop immédiat.

### D12 — Le plafonnement reste, et n'est jamais redimensionné

`_accumulated_error` reste borné à `±error_threshold` à chaque cycle
(`algorithm.py:222-227`, comportement actuel conservé). Ce n'est pas une
tolérance d'implémentation, c'est une **condition du modèle** : sans lui, une
accumulation de 10 conservée à travers un passage vers le niveau `fast` (seuil 2)
rendrait la décision de stop inévitable et sans rapport avec la situation
observée.

Le plafond est réappliqué avec le seuil **courant**, jamais avec l'ancien, et
l'accumulation n'est jamais mise à l'échelle. Deux propriétés en découlent, qui
sont exactement les deux scénarios de la spec :

- seuil abaissé sous l'accumulation → l'accumulation est ramenée au seuil, donc
  un stop devient possible immédiatement ;
- seuil relevé au-dessus de l'accumulation → l'accumulation garde sa valeur,
  donc le stop redevient improbable tant que l'écart ne s'est pas reconstitué.

*Alternative écartée* : redimensionner l'accumulation au prorata
(`accumulation × nouveau / ancien`) pour « préserver le pourcentage de
saturation ». Rejetée : cela fabriquerait une mesure qui n'a jamais été observée,
et surtout cela rendrait le sens Rapide → Lent capable de déclencher un stop
immédiat — un comble pour un réglage demandant moins de sensibilité.

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
- **Accumulation conservée à travers des réglages très différents** → Passer de
  `very_slow` (seuil 20) à `fast` (seuil 2) applique une intégrale déjà saturée à
  20 sur un seuil de 2 : la décision tombe au premier cycle. Ce n'est **pas** un
  effet indésirable mais la conséquence directe et voulue du modèle : l'écart
  avait été observé, et le nouveau réglage demande simplement une réaction plus
  rapide. Mitigation : aucune n'est nécessaire ; le comportement est couvert par
  le scénario `A faster level can detect a stop on the next cycle`, et son
  symétrique `A slower level cannot detect a stop on the next cycle` garantit
  que le sens inverse ne déclenche rien. Le plafonnement (D12) est ce qui rend
  cette asymétrie fiable.
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
