# Design

## Contexte

Le plugin résout les paramètres de détection en trois couches (`plugin defaults → global → dédié`), implémentées une seule fois dans `models.effective_config` et consommées en un seul point par le manager. Le niveau sélectionné est ensuite traduit en une paire `(dt_min, error_threshold)` par `resolve_params(level)` dans `algorithm.py`.

La phase 1 a scellé la règle suivante : le niveau est un entier énuméré, mappé par une table statique. Les valeurs custom n'existent pas. La requirement « Phase-2 parameter readiness » de la spec l'a formalisé.

Le code est structuré pour que l'ajout d'un niveau ne touche qu'une seule fonction : `set_level` → `resolve_params` → le reste ne lit que `LevelParams`. Les attributs publiés (`ATTR_DTMIN`, `ATTR_ACCUMULATED_ERROR_THRESHOLD`) reflètent déjà les valeurs effectives et n'ont pas à changer.

## Objectifs / Non-objectifs

**Objectifs :**
- Ajouter `personnalise` comme sixième niveau au vocabulaire des niveaux.
- Permettre à l'utilisateur de définir `dt_min` et `error_threshold` pour un thermostat donné.
- **Afficher en permanence** ces deux champs dans le formulaire (global et dédié) : l'utilisateur peut les consulter et les modifier sans avoir à re-ouvrir la configuration.
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

### 4. Champs `dt_min` et `error_threshold` toujours visibles

**Décision A1 (révisée)** : les deux sélecteurs `NumberSelector` sont affichés **en permanence** dans le formulaire global ET dédié, quel que soit le niveau sélectionné. L'utilisateur peut donc :

- consulter les valeurs courantes à tout moment (pré-remplies depuis l'entry courante, ou les valeurs par défaut plugin SLOW 30/10 si l'entry est vierge) ;
- les modifier sans avoir à re-ouvrir la configuration ni à passer par « Personnalisé » en premier ;
- basculer sur **Personnalisé** et **appliquer immédiatement** ses valeurs (la garde `resolve_params(level, config)` ne lit ces clés que si `level == LEVEL_PERSONNALISE`, les niveaux nommés continuent d'utiliser leurs tables statiques).

Ce choix évite le piège de l'option « pré-remplir au switch » (qui nécessitait un submit vide puis une re-ouverture pour saisir les valeurs) et ne dépend pas de la sémantique « conditionnelle d'affichage » de l'UI HA, ce qui rend le formulaire prévisible.

Le code est minimal : les deux champs sont ajoutés au `fields` par défaut de `_options_schema`, et le filtre `parameters_only` (entrée dédiée) conserve en plus de `CONF_LEVEL` les clés `CONF_DT_MIN` et `CONF_ERROR_THRESHOLD`.

```python
# options flow (global et dédié)
fields[CONF_DT_MIN] = vol.Optional(
    CONF_DT_MIN, default=defaults.get(CONF_DT_MIN, DEFAULT_DT_MIN),
)(selector.NumberSelector(selector.NumberSelectorConfig(min=5, max=120, unit_of_measurement="min", mode="box")))
fields[CONF_ERROR_THRESHOLD] = vol.Optional(
    CONF_ERROR_THRESHOLD, default=defaults.get(CONF_ERROR_THRESHOLD, DEFAULT_ERROR_THRESHOLD),
)(selector.NumberSelector(selector.NumberSelectorConfig(min=1, max=50, step=0.5, mode="box")))
```

La garde défensive `_clamp_numbers` reste en second rideau pour les soumissions programmatiques (l'UI `NumberSelector` rejette déjà toute valeur hors de `[5, 120]` / `[1, 50]`).

Conséquences observables :

- `vol.Optional(default=...)` **popule** les clefs `dt_min` / `error_threshold` dans l'entry même lorsque le niveau n'est pas `personnalise`. Les valeurs sont présentes mais ignorées par `resolve_params` tant que le niveau est nommé, ce qui est la même sémantique que la décision C1 déjà validée (Risque 2).
- Un utilisateur peut donc stocker ses valeurs custom **avant** de basculer sur Personnalisé — comportement cohérent avec « les valeurs sont prêtes lorsqu'on les veut ».

**Retrait** du pré-remplissage par injection (ancien paragraphe) : l'helper `_prefill_custom_params` et l'import `DT_MIN`/`ERROR_THRESHOLD` dans `config_flow.py` sont supprimés (le niveau nommé ne lit pas `config` et la sémantique « héritage du niveau précédent » est devenue inutile).

### 5. Schéma non conditionnel sur le niveau

Le schéma d'options est désormais **non conditionnel** sur le niveau : les deux `NumberSelector` font partie du `fields` par défaut. Le sélecteur de niveau reste dans le formulaire et le filtrage `parameters_only` (entrée dédiée) conserve les trois clés de détection (`CONF_LEVEL`, `CONF_DT_MIN`, `CONF_ERROR_THRESHOLD`), tout en excluant `CONF_STOP_MODE` / `CONF_ENABLED` (mémorisés par l'entité) et `CONF_VTHERM_UNIQUE_ID`.

La conséquence est que le formulaire est identique à tous les niveaux : aucune logique d'injection au submit, aucune dépendance au niveau *au moment de l'affichage*.

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

**Risque 1 — Les valeurs stockées pour un niveau nommé.** `vol.Optional(default=...)` remplit systématiquement `entry.options` avec les clés `dt_min` / `error_threshold` même lorsque le niveau n'est pas `personnalise`. Le comportement est documenté (Risque 2 / décision C1) : les valeurs sont présentes mais ignorées par `resolve_params` tant que le niveau est nommé. Un utilisateur qui inspecte `entry.options` verra deux clés « inutilisées » pour un niveau `slow` ; c'est acceptable car cela évite de perdre les valeurs custom lors d'un passage successif à `personnalise`.

**Risque 2 — Les champs `dt_min` et `error_threshold` restent dans `entry.options` après un retour de `personnalise` vers un niveau prédéfini.** C'est un compromis assumé (décision C1) : les clés persistent, `effective_config` les résout toujours, mais `resolve_params` ne les lit que quand `level == LEVEL_PERSONNALISE`. Aucun comportement indésirable, mais un utilisateur qui inspecte l'entry pourra y voir des clés apparemment « inutilisées » quand le niveau est `slow`.

**Risque 3 — La cascade résout `dt_min` et `error_threshold` comme des paramètres de détection.** Une entry globale peut donc porter des valeurs custom qui s'appliquent à tous les thermostats. C'est cohérent avec la sémantique du niveau `personnalise` : c'est un paramètre de détection, pas un défaut d'état. Mais c'est plus permissif qu'attendu d'un utilisateur qui pense « je règle ça pour tout le monde » : il faudra le documenter.

**Risque 4 — `resolve_params` reçoit désormais `config`.** Les tests unitaires de l'algorithme appellent `resolve_params(level)` directement. Ils doivent être adaptés. C'est une refactorisation mineure mais nécessaire.

## Plan de migration

Aucune migration d'entrée n'est requise. Les entrées existantes n'ont pas les nouvelles clés ; la résolution les ignore tant que le niveau n'est pas `personnalise`. Il suffit de recharger l'intégration.

Les entrées existantes portant `auto_start_stop_none` (niveau « Aucun ») sont fondues automatiquement vers les valeurs SLOW par `normalize_level` (la valeur n'est plus dans `LEVELS`). Aucun bump de `VERSION`, aucune écriture dans `entry.data` — la valeur stockée reste `auto_start_stop_none` mais résout comme SLOW.

Rollback : le retour au niveau `personnalise` n'est pas nécessaire. Le niveau est optionnel et aucun comportement n'est modifié tant que le utilisateur ne l'a pas sélectionné. Le niveau « Aucun » est retiré mais sa valeur stockée continue de résoudre valablement (SLOW), donc un rollback de code ne casse pas une installation existante.

## Questions ouvertes

Néant.
