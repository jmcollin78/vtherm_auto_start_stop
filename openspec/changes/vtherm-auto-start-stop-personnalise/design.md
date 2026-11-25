# Design

## Contexte

Le plugin résout les paramètres de détection en trois couches (`plugin defaults → global → dédié`), implémentées une seule fois dans `models.effective_config` et consommées en un seul point par le manager. Le niveau sélectionné est ensuite traduit en une paire `(dt_min, error_threshold)` par `resolve_params(level)` dans `algorithm.py`.

La phase 1 a scellé la règle suivante : le niveau est un entier énuméré, mappé par une table statique. Les valeurs custom n'existent pas. La requirement « Phase-2 parameter readiness » de la spec l'a formalisé.

Le code est structuré pour que l'ajout d'un niveau ne touche qu'une seule fonction : `set_level` → `resolve_params` → le reste ne lit que `LevelParams`. Les attributs publiés (`ATTR_DTMIN`, `ATTR_ACCUMULATED_ERROR_THRESHOLD`) reflètent déjà les valeurs effectives et n'ont pas à changer.

## Objectifs / Non-objectifs

**Objectifs :**
- Ajouter `personnalise` comme sixième niveau au vocabulaire des niveaux.
- Permettre à l'utilisateur de définir `dt_min` et `error_threshold` pour un thermostat donné.
- Pré-remplir ces champs depuis le niveau précédent au moment du switch.
- Maintenir la rétro-compatibilité stricte : aucune migration des entrées existantes, aucune modification de la UI Card.

**Non-objectifs :**
- Ne pas modifier le cœur VTherm ou la UI Card.
- Ne pas ajouter de niveaux au-delà de `personnalise`.
- Ne pas créer de nouveaux entités ou contrôles.
- Ne pas introduire de configuration multi-niveaux (ex. différents seuils pour le chauffage et le refroidissement).

## Décisions

### 1. Clés de configuration

Deux nouvelles clés :
```
CONF_DT_MIN          = "auto_start_stop_dt_min"
CONF_ERROR_THRESHOLD = "auto_start_stop_error_threshold"
```

Elles suivent la convention snake_case du plugin et se distinguent des attributs publiés (`ATTR_DTMIN`, `ATTR_ACCUMULATED_ERROR_THRESHOLD`), qui conservent leur nom verbatim hérité du core. Les clés de config entry sont des noms stables internes ; les attributs sont un contrat externe avec la carte et les automatisations.

Une constante dédiée `CUSTOM_PARAMETER_KEYS = (CONF_DT_MIN, CONF_ERROR_THRESHOLD)` est introduite dans `models.py` pour la cascade de résolution. `PARAMETER_KEYS` ne change pas : il contient `(CONF_LEVEL,)` et est utilisé indépendamment pour la détection de « complétude d'une entry dédiée » dans `__init__.py` (test `all(key in config for key in PARAMETER_KEYS)`), qu'on ne peut pas modifier sans casser la logique de reload.

Dans `effective_config`, la layer dédiée est agrégée sur `PARAMETER_KEYS + CUSTOM_PARAMETER_KEYS`, et la layer globale sur `CONFIG_KEYS + CUSTOM_PARAMETER_KEYS` (les clés custom apparaissent aussi au niveau global : un thermostat couvé globalement hérite éventuellement des seuils custom du global). La cascade reste : plugin defaults → global → dédié.

### 2. Valeurs par défaut plugin

`default_config()` ajoute :
```python
CONF_DT_MIN: DEFAULT_DT_MIN          # 30.0 (valeur du niveau SLOW)
CONF_ERROR_THRESHOLD: DEFAULT_ERROR_THRESHOLD  # 10.0 (valeur du niveau SLOW)
```

Ces valeurs par défaut ne sont pas un comportement visible : elles ne s'appliquent qu'à un niveau `personnalise` sans valeurs custom dans l'entry. Ce cas ne se produit qu'au moment du switch, et précisément dans les intervalles où l'options flow injecte les valeurs du niveau précédent.

### 3. Résolution des paramètres custom

`resolve_params` change de signature : elle reçoit en plus la configuration effective.

```python
def resolve_params(level: str, config: dict[str, Any]) -> LevelParams:
    if level == LEVEL_PERSONNALISE:
        dt_min = config.get(CONF_DT_MIN, DEFAULT_DT_MIN)
        threshold = config.get(CONF_ERROR_THRESHOLD, DEFAULT_ERROR_THRESHOLD)
        return LevelParams(float(dt_min), float(threshold))
    if level in DT_MIN:
        return LevelParams(DT_MIN[level], ERROR_THRESHOLD[level])
    _LOGGER.debug(...)
    return LevelParams(DT_MIN[LEVEL_SLOW], ERROR_THRESHOLD[LEVEL_SLOW])
```

Le manager passe `config` (résultat de `effective_config`) à chaque appel de `set_level` ou directement lors de la construction de l'algorithme. Le `fallback` par défaut (valeurs de `SLOW`) est un garde-fou pour un entry corrompu ou obsolète — il ne se produit normalement jamais après un switch propre fait par les options flow.

### 4. Pré-remplissage au switch dans l'`options flow`

Le point clé du comportement attendu (décision A1) : quand l'utilisateur change le niveau à `personnalise`, les champs `dt_min` et `error_threshold` doivent se pré-remplir avec les valeurs du niveau sélectionné *avant* le switch.

Le mécanisme s'effectue dans `auto_options_flow.async_step_init` : avant de traiter le submit, on lit `self._config_entry.data[CONF_LEVEL]` (l'ancienne valeur). Si le `user_input` soumis contient `CONF_LEVEL == LEVEL_PERSONNALISE` et que les champs custom ne sont **pas** dans le `user_input` (c'est le cas normal : l'UI ne les affichait pas avant le submit), on injecte les valeurs du niveau précédent dans le `data` final.

```python
# Dans async_step_init, après la validation de user_input
old_level = self._config_entry.data.get(CONF_LEVEL)
new_level = user_input.get(CONF_LEVEL)
if new_level == LEVEL_PERSONNALISE and old_level != LEVEL_PERSONNALISE:
    # Injecte les valeurs du niveau précédent si l'utilisateur ne les a pas modifiées
    if CONF_DT_MIN not in user_input:
        user_input[CONF_DT_MIN] = DT_MIN.get(old_level, DEFAULT_DT_MIN)
    if CONF_ERROR_THRESHOLD not in user_input:
        user_input[CONF_ERROR_THRESHOLD] = ERROR_THRESHOLD.get(old_level, DEFAULT_ERROR_THRESHOLD)
```

Le même mécanisme s'applique à la création d'une entrée dédiée via `async_step_thermostat_options`, où le niveau précédent est celui seedé par l'`entry` du core.

Le cas où l'utilisateur reste sur `personnalise` et modifie les valeurs : les champs sont déjà dans le `user_input`, aucune injection n'a lieu.

### 5. Schéma conditionnel

`_options_schema` accepte un nouveau paramètre ou déduit de `defaults[CONF_LEVEL]` si les champs custom doivent apparaître :

```python
if defaults.get(CONF_LEVEL) == LEVEL_PERSONNALISE:
    fields[CONF_DT_MIN] = selector.NumberSelector(
        selector.NumberSelectorConfig(min=5, max=120, unit_of_measurement="min")
    )
    fields[CONF_ERROR_THRESHOLD] = selector.NumberSelector(
        selector.NumberSelectorConfig(min=1, max=50, step=0.5)
    )
```

Le comportement est statique par affichage : le formulaire recalculé est celui du niveau *au moment de l'affichage*, pas celui que le utilisateur choisira en cochant le select. Le sélecteur de niveau lui-même reste dans le formulaire ; les champs custom apparaissent si le niveau *enregistré* est déjà `personnalise`. Si l'utilisateur passe de `slow` à `personnalise` sans recharger, le premier submit enregistre le niveau `personnalise` avec les valeurs injectées par l'étape 4, et le formulaire suivant affiche les champs custom.

### 6. Vocabulaire

```python
LEVEL_PERSONNALISE = "auto_start_stop_personnalise"
LEVELS = [LEVEL_VERY_SLOW, LEVEL_SLOW, LEVEL_MEDIUM, LEVEL_FAST, LEVEL_PERSONNALISE]
TYPE_LEVEL = Literal[..., "auto_start_stop_personnalise"]
```

`normalize_level` est inchangé : les nouvelles valeurs sont reconnues par l'ajout à `LEVELS`.

### 7. `LevelParams` et `set_level`

`set_level` ne change pas de signature. Le manager, qui reçoit `config` depuis `effective_config`, appelle :

```python
self._algorithm.set_params(normalize_level(level), effective_config)
```

Une nouvelle méthode `set_params(level, config)` remplace `set_level(level)` dans le manager. L'interface publique de l'algorithme est enrichie, pas cassée : les tests existants passent toujours en adaptant les appels.

`dt_min` et `accumulated_error_threshold` (propriétés de l'algorithme) sont désormais calculées à partir des `LevelParams` résolus et non plus lues des tables statiques. Le comportement observable est identique pour les niveaux nommés.

### 7b. Retrait du niveau « Aucun »

Le niveau « Aucun » (`LEVEL_NONE`, valeur `auto_start_stop_none`) est retiré du sélecteur car l'activation est déjà pilotée par l'interrupteur de la fonction : un thermostat désactivé n'accumule rien et n'arrête rien, quel que soit son niveau. Le niveau « Aucun » n'apportait qu'une redondance.

Le mécanisme de fondu repose sur `normalize_level` : elle renvoie `DEFAULT_LEVEL` (SLOW) pour toute valeur absente de `LEVELS`. En retirant `LEVEL_NONE` de `LEVELS`, toute entry existante portant `auto_start_stop_none` est résolue automatiquement vers les valeurs SLOW (30 min / 10) au prochain rechargement, sans migration d'entrée ni bump de `VERSION`.

Concrètement :
- `LEVELS` et `TYPE_LEVEL` ne listent plus `LEVEL_NONE`.
- Les tables `DT_MIN` et `ERROR_THRESHOLD` de l'algorithme perdent leur entrée `LEVEL_NONE` (la valeur inconnue passe par le fallback SLOW de `resolve_params`).
- `__init__` de l'algorithme passe par `normalize_level(LEVEL_NONE)` → SLOW, ce qui est cohérent : l'état initial de toute instance est le niveau par défaut.
- Les libellés de niveau dans `translations/*.json` retrait du libellé « Aucun ».

**Conséquence testée** : un test dédié vérifie que `normalize_level("auto_start_stop_none") == LEVEL_SLOW` et que `resolve_params` produit les paires SLOW pour cette valeur. Les tests existants qui utilisent `LEVEL_NONE` comme niveau de test (par ex. `test_manager.py:426` qui crée une entry globale en `LEVEL_NONE` pour la désactiver) sont adaptés pour utiliser un niveau valide + l'interrupteur off, ou conservés pour vérifier expressément le fondu.

## Risques / Compromis

**Risque 1 — Le formulaire n'affiche pas les champs au premier passage sur `personnalise`.** L'UI du sélecteur HA ne recharge pas le formulaire en direct quand le utilisateur change une option : le utilisateur devra soumettre une première fois (qui injecte les valeurs), puis le formulaire suivant affiche les champs. C'est acceptable : le comportement est cohérent avec le reste du flow (changement de mode d'arrêt qui n'a pas de champ conditionnel).

**Risque 2 — Les champs `dt_min` et `error_threshold` restent dans `entry.options` après un retour de `personnalise` vers un niveau prédéfini.** C'est un compromis assumé (décision C1) : les clés persistent, `effective_config` les résout toujours, mais `resolve_params` ne les lit que quand `level == LEVEL_PERSONNALISE`. Aucun comportement indésirable, mais un utilisateur qui inspecte l'entry pourra y voir des clés apparemment « inutilisées » quand le niveau est `slow`.

**Risque 3 — La cascade résout `dt_min` et `error_threshold` comme des paramètres de détection.** Une entry globale peut donc porter des valeurs custom qui s'appliquent à tous les thermostats. C'est cohérent avec la sémantique du niveau `personnalise` : c'est un paramètre de détection, pas un défaut d'état. Mais c'est plus permissif qu'attendu d'un utilisateur qui pense « je règle ça pour tout le monde » : il faudra le documenter.

**Risque 4 — `resolve_params` reçoit désormais `config`.** Les tests unitaires de l'algorithme appellent `resolve_params(level)` directement. Ils doivent être adaptés. C'est une refactorisation mineure mais nécessaire.

## Plan de migration

Aucune migration d'entrée n'est requise. Les entrées existantes n'ont pas les nouvelles clés ; la résolution les ignore tant que le niveau n'est pas `personnalise`. Il suffit de recharger l'intégration.

Les entrées existantes portant `auto_start_stop_none` (niveau « Aucun ») sont fondues automatiquement vers les valeurs SLOW par `normalize_level` (la valeur n'est plus dans `LEVELS`). Aucun bump de `VERSION`, aucune écriture dans `entry.data` — la valeur stockée reste `auto_start_stop_none` mais résout comme SLOW.

Rollback : le retour au niveau `personnalise` n'est pas nécessaire. Le niveau est optionnel et aucun comportement n'est modifié tant que le utilisateur ne l'a pas sélectionné. Le niveau « Aucun » est retiré mais sa valeur stockée continue de résoudre valablement (SLOW), donc un rollback de code ne casse pas une installation existante.

## Questions ouvertes

Néant.
