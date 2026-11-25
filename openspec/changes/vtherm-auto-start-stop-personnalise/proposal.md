# Proposal

## Why

Phase 1 du plugin a livré cinq niveaux de détection prédéfinis (Aucun → Très lent → Rapide). L'utilisateur n'a aucun moyen de régler finement le délai minimum (`dt_min`) ni le seuil d'erreur accumulée (`error_threshold`) pour un thermostat donné. Cette fonctionnalité est déjà prémontée dans le code (`resolve_params` est le point d'extension documenté) et a été explicitement exclue de la phase 1.

Ce change ajoute un sixième niveau — **Personnalisé** — qui laisse l'utilisateur saisir librement les deux paramètres de détection pour chaque thermostat concerné. Le niveau « Aucun » est par l'occasion supprimé : l'activation est déjà maîtrisée par l'interrupteur de la fonction, le niveau ne sert plus à rien. Les niveaux prédéfinis restants sont intacts et la rétro-compatibilité est stricte : les entrées existantes ne requièrent aucune migration.

## What Changes

- Un nouveau niveau `PERSONNALISE` (« Personnalisé ») est ajouté au vocabulaire des niveaux.
- Le niveau `AUCUN` (`auto_start_stop_none`) est retiré du sélecteur. Les entrées existantes portant cette valeur la résolvent vers les valeurs par défaut du plugin (les valeurs du niveau SLOW : 30 min / 10) via le mécanisme de retour arrière des valeurs inconnues, sans migration.
- Deux clés de configuration (`dt_min`, `error_threshold`) sont ajoutées à la cascade de résolution (déploiement → global → dédié).
- `resolve_params` est étendu : pour `PERSONNALISE`, les valeurs sont lues des clés custom de la configuration effective ; en l'absence de ces clés, les valeurs du niveau précédent sont utilisées comme retour arrière.
- Le schéma d'options du flux de configuration passe en mode conditionnel : quand le niveau sélectionné vaut `PERSONNALISE`, deux `NumberSelector` (délai 5 → 120 min, seuil 1 → 50) apparaissent dans le même formulaire.
- L'`options flow` pré-remplit ces champs depuis les valeurs correspondantes du niveau actuellement sélectionné (héritage du niveau précédent) au moment où l'utilisateur bascule sur Personnalisé.
- Les traductions FR/EN sont mises à jour (ajout du libellé Personnalisé, retrait du libellé Aucun).

## Capabilities

### New Capabilities

(néant — cette évolution s'inscrit dans la capacité existante)

### Modified Capabilities

- `auto-start-stop-plugin` : ajout du niveau `PERSONNALISE` à la résolution des paramètres de détection, aux clés de configuration, au flux de configuration et aux traductions.

## Impact

- `custom_components/vtherm_auto_start_stop/const.py` — nouveau niveau `PERSONNALISE`, nouvelles clés de config, de `LEVELS` et de `TYPE_LEVEL` ; retrait de `LEVEL_NONE` du vocabulaire exposé.
- `custom_components/vtherm_auto_start_stop/models.py` — `effective_config` gère les deux nouvelles clés dans la cascade ; `default_config` les porte. `normalize_level` fondu d'office vers le défaut pour l'ancienne valeur `auto_start_stop_none`.
- `custom_components/vtherm_auto_start_stop/algorithm.py` — `resolve_params` accepte `PERSONNALISE` et lit les valeurs custom ; retrait des entrées `LEVEL_NONE` des tables `DT_MIN` / `ERROR_THRESHOLD` (la valeur résout désormais par fallback).
- `custom_components/vtherm_auto_start_stop/config_flow.py` — `_options_schema` conditionnel ; `options flow` hérite des valeurs du niveau précédent.
- `custom_components/vtherm_auto_start_stop/translations/fr.json`, `en.json` — nouveaux libellés, retrait du libellé du niveau Aucun.
- `tests/` — adaptation des tests qui référencent `LEVEL_NONE` (algorithm, models, manager, vocabulary).
- Aucun changement dans le cœur VTherm, dans la UI Card, ou dans les attributs publiés (`ATTR_DTMIN` / `ATTR_ACCUMULATED_ERROR_THRESHOLD` reflètent naturellement les valeurs effectives).
