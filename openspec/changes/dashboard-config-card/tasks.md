# Tasks

## 1. Dépendance optionnelle, chemin statique et enregistrement conditionnel

- [ ] 1.1 Ajouter `"after_dependencies": ["vtherm_dashboard"]` à
      `custom_components/vtherm_auto_start_stop/manifest.json`, sans toucher à
      `dependencies`, et incrémenter la version. Vérifier que le fichier reste un
      JSON valide et que `dependencies` vaut toujours `["versatile_thermostat"]`.
- [ ] 1.2 Ajouter `STATIC_URL`, `WWW_DIR` et `DASHBOARD_DOMAIN` dans `const.py`,
      sur le modèle du plugin d'exemple (`f"/{DOMAIN}_static"`). Vérifier que
      `pytest tests/test_vocabulary.py` passe toujours.
- [ ] 1.3 Dans `async_setup`, enregistrer le chemin statique
      (`StaticPathConfig(STATIC_URL, str(WWW_DIR), cache_headers=False)`) puis
      appeler `register_ui_plugin(...)` uniquement si
      `"vtherm_dashboard" in hass.config.components`. Vérifier par un test dans
      `tests/test_setup.py` que le chemin statique et l'enregistrement ont lieu
      quand le domaine est présent, et qu'aucun des deux n'a lieu quand il est
      absent, sans erreur ni avertissement journalisé.
- [ ] 1.4 Documenter dans `README.md` et `README-fr.md` une section « Fonctionne
      sans le dashboard » : les entités restent utilisables seules, la carte et le
      widget n'apparaissent pas, et la plus-value du dashboard (édition groupée,
      résumé par thermostat). Vérifier que la section existe dans les deux
      fichiers et qu'aucun des deux ne présente le dashboard comme obligatoire.

## 2. Racine de build `ui/`

- [ ] 2.1 Créer `ui/package.json` (privé, `type: module`, scripts `build`,
      `typecheck`, `test`, dépendances `@vtherm/dashboard-sdk` et `lit`) et
      `ui/tsconfig.json` en mode strict. Vérifier que `npm install` puis
      `npm run typecheck` réussissent depuis `ui/`.
- [ ] 2.2 Créer `ui/vite.config.ts` en mode lib : entrée `src/main.ts`, sortie
      `../custom_components/vtherm_auto_start_stop/www`, format ES, nom de fichier
      `vtherm-auto-start-stop.js`, `@vtherm/dashboard-sdk` laissé externe, et un
      serveur de développement avec `Access-Control-Allow-Origin: *`. Vérifier que
      `npm run build` produit exactement
      `custom_components/vtherm_auto_start_stop/www/vtherm-auto-start-stop.js`.
- [ ] 2.3 Vérifier que `custom_components/vtherm_auto_start_stop/www/` est bien
      livré par HACS : contrôler que le fichier construit n'est pas exclu par
      `.gitignore` ni par le packaging, et que l'arborescence reste compatible
      avec `content_in_root: false` de `hacs.json`.

## 3. Prédicat de couverture partagé et statut de section

- [ ] 3.1 Implémenter `covered(hass, thermostatId)` dans
      `ui/src/entities.ts` : les cinq clés (`auto_start_stop_enable`,
      `_stop_mode`, `_level`, `_dtmin`, `_error_threshold`) présentes dans
      `getEntryEntities(...).byKey`, dans un `try/catch` renvoyant `false`.
      Vérifier par un test vitest que les cinq clés donnent `true`, qu'une clé
      manquante donne `false`, et qu'un `hass` provoquant une exception donne
      `false` au lieu de lever.
- [ ] 3.2 Implémenter `sectionStatus(context)` retournant `{kind:"off"}` quand
      `auto_start_stop_enable` n'est pas `on`, `{kind:"incomplete", missing:n}`
      quand un des deux numériques n'est pas lisible, `{kind:"complete"}`
      sinon, et `undefined` quand les entités manquent. Vérifier par un test
      vitest les quatre branches, et qu'aucun retour ne porte `kind:"inherited"`.

## 4. Carte `thermostat_config`

- [ ] 4.1 Créer l'élément Lit de la carte dans `ui/src/config-card.ts` : rendu
      des cinq contrôles avec les composants Home Assistant
      (`ha-switch`, `ha-selector`), libellés et aides issus des catalogues,
      message de remplacement quand la couverture est fausse. Vérifier par un
      test vitest que les cinq contrôles sont rendus pour un thermostat couvert,
      et qu'un message de repli est rendu pour un thermostat non couvert.
- [ ] 4.2 Brancher chaque contrôle sur `hass.callService` avec écriture
      immédiate, et désactiver tous les contrôles quand `draft === undefined`
      (lecture seule). Vérifier par un test vitest que la modification d'un
      contrôle émet l'appel de service attendu sur la bonne entité, et qu'aucun
      contrôle n'est actionnable quand `draft` est indéfini.
- [ ] 4.3 Afficher les erreurs de service (`missing_configuration`,
      `invalid_auto_start_stop_option`, `invalid_auto_start_stop_bound`) dans un
      `ha-alert` associé au contrôle fautif, sans perdre la valeur précédente.
      Vérifier par un test vitest qu'un rejet de service rend le message
      traduit et laisse le contrôle sur son ancienne valeur.
- [ ] 4.4 Déclarer la contribution `thermostat_config` dans `ui/src/main.ts` :
      `id`, `titleKey`, `tag`, `placement: { after: "core_auto_start_stop.tab.main" }`,
      `on_missing: "last"`, `group: CORE_MENU_GROUPS.features`,
      `save_actions: "component"`, `visible` et `status` ; définir le tag avant
      `registerUiPlugin`. Vérifier qu'aucune contribution `remove:` ni `replace:`
      n'est émise, et que la carte ne dessine aucun pied Enregistrer/Annuler.

## 5. Widget `thermostat_widget`

- [ ] 5.1 Créer l'élément Lit du widget dans `ui/src/widget.ts` : état
      marche/arrêt, erreur accumulée rapportée au seuil, âge du dernier
      basculement, et niveau dérivé, dans une `ha-card`. Vérifier par un test
      vitest que les quatre informations sont rendues à partir des seuls
      attributs `auto_start_stop_manager.*` et
      `is_auto_start_stop_configured`.
- [ ] 5.2 Gérer les états dégradés : « — » pour une valeur absente (jamais `0`),
      disparition du widget quand la fonctionnalité est éteinte ou quand aucune
      entité source n'existe, et rendu uniquement sur changement d'une des
      entités du widget. Vérifier par des tests vitest couvrant les trois cas.
- [ ] 5.3 Déclarer la contribution `thermostat_widget` dans `ui/src/main.ts`
      avec `size: { columns: 1, rows: 2 }`,
      `placement: { after: "core_auto_start_stop.widget.auto_start_stop" }` et
      `on_missing: "last"`. Vérifier que la contribution déclare bien une taille
      1×2 et que le tag est défini avant l'enregistrement.

## 6. Traductions et finition du bundle

- [ ] 6.1 Créer les catalogues `ui/src/translations.ts` avec
      `defineTranslations(en, { fr })` et `export const { t }`, en couvrant tous
      les libellés, aides et messages d'erreur de la carte, du widget et des
      deux titres de contribution. Vérifier par un test vitest que les clés des
      deux catalogues sont identiques, qu'aucune valeur n'est vide et que le
      catalogue anglais est complet.
- [ ] 6.2 Reconstruire `www/vtherm-auto-start-stop.js` et vérifier qu'il
      correspond aux sources : `npm run build` depuis `ui/`, puis contrôle que le
      bundle ne contient pas `@vtherm/dashboard-sdk` (laissé externe) et que sa
      date de modification est postérieure à la dernière modification de
      `ui/src/`.

## 7. Vérification d'intégration

- [ ] 7.1 Exécuter `pytest` sur l'ensemble de `tests/` et vérifier que la suite
      reste verte, y compris `tests/test_setup.py` avec l'enregistrement
      conditionnel.
- [ ] 7.2 Exécuter `npm run typecheck`, `npm run test` et `npm run build` depuis
      `ui/`, puis vérifier que les trois réussissent et que le bundle produit est
      celui qui est committé.
- [ ] 7.3 Vérifier dans Home Assistant, dashboard absent, que l'intégration
      démarre et que les cinq entités restent utilisables ; puis dashboard
      installé, après rechargement, que la carte et le widget apparaissent pour un
      thermostat `over_climate` couvert, et pas pour un thermostat non couvert.
- [ ] 7.4 Exécuter `openspec validate "dashboard-config-card" --strict` et
      vérifier que la validation passe.

## Workflow follow-up

- Archiver le change une fois les exigences de revue du projet satisfaites.
- Vérifier le résultat archivé et la synchronisation de la spécification
  `auto-start-stop-dashboard`.
