# Proposal

## Why

Le `## Purpose` de `openspec/specs/auto-start-stop-plugin/spec.md` décrit encore
le plugin comme une « configuration layered from a global default down to a
per-thermostat instance ». Ce modèle a été supprimé par `parameters-as-entities`
(archivé le 2026-11-28) : une entrée ne porte plus aucun paramètre de détection,
elle ne fait que **couvrir** un thermostat et **semer** ses entités une fois.

La section contredit désormais les vingt exigences qui la suivent. Un lecteur qui
s'arrête au résumé — ou un agent qui charge la spec avant d'agir — en tire un
modèle faux : il cherchera une cascade de résolution qui n'existe plus.

Les exigences, elles, sont justes. Seul le résumé est en retard.

## What Changes

- Réécriture du `## Purpose` de `auto-start-stop-plugin/spec.md` pour décrire le
  modèle réel : couverture par une entrée globale ou dédiée, cinq contrôles par
  thermostat (activation, mode d'arrêt, préréglage de niveau, durée minimale et
  seuil d'erreur), niveau **dérivé** de la paire de paramètres, décision prise
  par le manager sur la déviation accumulée.
- Aucun autre changement. Aucune exigence, aucun scénario, aucun comportement.

## Capabilities

### New Capabilities

Aucune.

### Modified Capabilities

Aucune au sens d'OpenSpec : le change ne modifie pas d'exigence. La section
`## Purpose` n'appartient pas à la grammaire des deltas (`ADDED` / `MODIFIED` /
`REMOVED` / `RENAMED Requirements`), elle ne peut donc pas être exprimée par un
delta. Le change est déclaré avec `skip_specs: true` et le texte est édité
directement dans la spec principale par la tâche 1.1.

Ce choix est délibéré : fabriquer une exigence factice pour obtenir un delta
valide polluerait le contrat de comportement avec du contenu éditorial.

## Impact

**Spécifications** — `openspec/specs/auto-start-stop-plugin/spec.md`, section
`## Purpose` uniquement. Les exigences et leurs scénarios sont inchangés.

**Code, tests, doc utilisateur** — aucun impact. Le texte ne décrit que ce que le
code fait déjà, vérifié en production le 2026-11-25.

**Risque** — quasi nul : une réécriture de résumé est réversible d'un
`git checkout`, et rien ne la consomme à l'exécution.
