# Proposal

## Why

Le niveau de détection et ses deux paramètres (`dt_min`, `error_threshold`) vivent
aujourd'hui dans l'entrée de configuration du plugin, alors que l'activation et le
mode d'arrêt vivent déjà dans des entités. Cette asymétrie impose trois coûts :

- **Éditer un paramètre recharge des thermostats.** Chaque modification d'entrée
  passe par `_async_update_options` puis `_reload_thermostats`, qui appelle
  `async_reload` sur chaque entrée Versatile Thermostat concernée.
- **Rien n'est automatisable.** Un `dt_min` ou un niveau ne peut pas être piloté
  par script, automatisation ou interface utilisateur standard, faute d'entité.
- **L'UI tierce n'a aucune voie d'écriture.** Le dashboard ne peut ni griser, ni
  écrire ces valeurs sans API dédiée.

Le passage en entités supprime les trois d'un seul geste, et rend le modèle
cohérent : enable et stop_mode sont déjà des entités, les trois autres le
deviennent.

## What Changes

- **BREAKING** — Le niveau de détection cesse d'être une configuration stockée et
  devient une **étiquette dérivée** des deux paramètres. Un couple
  (`dt_min`, `error_threshold`) qui correspond à un niveau nommé donne ce niveau ;
  sinon le niveau vaut `personnalise`.
- **BREAKING** — Les paramètres `dt_min` et `error_threshold` deviennent deux
  entités `number` par thermostat couvert (`EntityCategory.CONFIG`, restauration
  d'état). Le manager les lit comme il lit déjà l'activation et le mode d'arrêt.
- **BREAKING** — Passer à un niveau nommé **écrase** les valeurs personnalisées.
  L'exigence « Custom value persistence across level switches » est supprimée :
  elle protégeait un état qui n'existe plus.
- **BREAKING** — La cascade de configuration (défauts du plugin → instance globale
  → instance dédiée) est supprimée pour les paramètres de détection. L'entrée ne
  porte plus que la **couverture** du thermostat et les valeurs de **semence**
  initiales, comme elle le fait déjà pour l'activation et le mode d'arrêt.
- Le `select` de niveau devient un **préréglage** : le choisir écrit les deux
  paramètres puis publie l'étiquette dérivée. Il n'est plus une source de vérité.
- Le manager devient la **source unique de vérité** ; les entités en sont des
  vues. Changer de niveau met les cinq contrôles à jour d'un seul geste, sans
  état intermédiaire visible.
- **Changer un paramètre ne réinitialise plus la somme des erreurs.** Elle mesure
  un écart de température réellement observé ; `dt_min` et le seuil sont des
  critères de lecture appliqués à cette mesure, pas la mesure elle-même. Jeter
  l'accumulation à chaque ajustement obligeait l'utilisateur à attendre un cycle
  complet après chaque essai de réglage. La somme reste **plafonnée** au seuil
  courant : passer à un niveau plus rapide peut donc déclencher une détection dès
  le cycle suivant, tandis que passer à un niveau plus lent ne le peut pas — les
  deux comportements sont spécifiés séparément.
- `available = False` est explicitement exclu comme mécanisme de contrôle : un
  service visant une entité indisponible est filtré en silence par Home
  Assistant. Un paramètre hors niveau personnalisé reste disponible et lisible.
- L'attribut `auto_start_stop_manager.auto_start_stop_level` continue d'être
  publié, dérivé, pour la compatibilité des cartes et de l'index d'attributs.
- Migration : les valeurs `level`, `dt_min`, `error_threshold` présentes dans les
  entrées existantes initialisent les entités au premier démarrage, sans écraser
  un état restauré.

Hors périmètre, traité dans le change `dashboard-config-card` :

- la carte du dashboard Versatile Thermostat, son hook de contribution et son
  inscription via `register_ui_plugin` ;
- le retrait des contributions natives `core_auto_start_stop` devenues legacy.

## Capabilities

### New Capabilities

Aucune. Le changement reste dans la capacité existante du plugin : c'est le même
comportement configurable, stocké ailleurs.

### Modified Capabilities

- `auto-start-stop-plugin` : la résolution de configuration, le flow de
  configuration dédiée, la persistance des valeurs personnalisées, les bornes de
  paramètres, la liste des entités publiées et le niveau publié changent de
  nature.

`auto-start-stop-delegation` est volontairement laissée intacte : le core ne lit
ni n'écrit de paramètre de détection, il se contente de laisser le niveau intact
dans l'entrée du thermostat. Son comportement observable ne bouge pas.

## Impact

**Code** — `custom_components/vther_auto_start_stop/` :

| Fichier                         | Nature                                                                               |
| ------------------------------- | ------------------------------------------------------------------------------------ |
| `number.py`                     | nouveau : deux entités `dt_min` et `error_threshold`                                 |
| `select.py`                     | étendu : le niveau devient un préréglage qui écrit les paramètres                    |
| `models.py`                     | réduit : cascade et résolution en couches remplacées par la dérivation et la semence |
| `manager.py`                    | `apply_level` atomique, lecture des paramètres depuis les entités                    |
| `registry.py`                   | création et réconciliation des deux nouvelles entités                                |
| `config_flow.py`                | réduit : sélection du thermostat et valeurs de semence seulement                     |
| `__init__.py`                   | suppression de `_reload_thermostats` et `_async_update_options`                      |
| `const.py`                      | clés des nouvelles entités, tables inverse de dérivation                             |
| `strings.json`, `translations/` | libellés des entités ajoutées                                                        |

**Tests** — `tests/` : `test_config_flow.py` et `test_models.py` sont réécrits ;
`test_setup.py`, `test_entity_state.py`, `test_manager.py` et `test_registry.py`
sont adaptés ; nouveaux tests de dérivation et d'atomicité.

**Spécifications** — remplace cinq exigences de `auto-start-stop-plugin` et en
ajoute deux ; vérifie `auto-start-stop-delegation`.

**Dépendances** — aucune nouvelle. `vtherm_api >= 0.13.1` inchangé.

**Hors dépôt** — la carte (`dashboard-config-card`) touchera `vtherm_dashboard` ;
elle est volontairement séparée pour que ce change-ci reste réversible seul.
