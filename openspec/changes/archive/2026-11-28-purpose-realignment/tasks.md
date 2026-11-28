# Tasks

## 1. Réalignement du Purpose

- [x] 1.1 Réécrire la section `## Purpose` de
  `openspec/specs/auto-start-stop-plugin/spec.md` pour décrire la couverture par
  entrée (globale ou dédiée), les cinq contrôles par thermostat couvert et la
  décision du manager sur la déviation accumulée, en y conservant le niveau comme
  étiquette dérivée de la paire de paramètres ; vérifier qu'aucune mention de
  résolution en couches, de cascade ou de défauts hérités ne subsiste dans la
  section.
- [x] 1.2 Vérifier que seule la section `## Purpose` a changé :
  `rtk git diff --stat openspec/specs/auto-start-stop-plugin/spec.md` doit
  n'annoncer qu'une poignée de lignes, et
  `rtk openspec validate --specs --store vtherm-auto-start-stop` doit rester
  vert, avec le même nombre d'exigences qu'avant (20).
- [x] 1.3 Vérifier la cohérence avec les deux specs sœurs : relire le `## Purpose`
  de `auto-start-stop-delegation` et de `thermostat-runtime-api` pour confirmer la
  même forme (un paragraphe court, sans liste ni tableau).

## 2. Clôture

- [x] 2.1 Archiver le change : `openspec archive purpose-realignment --store
  vtherm-auto-start-stop`, puis vérifier que
  `openspec validate --all --strict --store vtherm-auto-start-stop` ne laisse
  plus que l'erreur attendue de `dashboard-config-card`.
