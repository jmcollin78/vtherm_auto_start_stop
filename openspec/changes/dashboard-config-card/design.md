# Design

## Context

Voir `proposal.md` — Why pour la motivation, et
`specs/auto-start-stop-dashboard/spec.md` pour le contrat de comportement.

État actuel, tel qu'il contraint la conception :

- Le plugin n'a **ni** chemin statique **ni** enregistrement UI :
  `async_setup` ne fait qu'enregistrer la factory, `async_setup_entry` réconcilie
  les entités et forward les plateformes.
- Les cinq contrôles sont des entités rattachées à l'appareil du thermostat
  (`thermostat_device()`), donc découvrables côté navigateur par
  `getEntryEntities(hass, entryId)`, qui retrouve l'appareil dont les
  `identifiers` contiennent `[versatile_thermostat, entryId]`.
- Les données de détection ne sont disponibles que comme **attributs publiés**
  sur le `climate` du thermostat : `is_auto_start_stop_configured` et la section
  `auto_start_stop_manager.*`. Le core invoque bien
  `manager.add_custom_attributes(...)` à chaque reconstruction des attributs.
- Le dashboard expose un SDK (`@vtherm/dashboard-sdk` `0.1.0-beta4`) et un
  plugin d'exemple à imiter (`examples/vtherm_sample_plugin`).

Contraintes du runtime du dashboard, vérifiées dans son code, qui ont dicté
plusieurs décisions :

| Contrainte | Conséquence |
| --- | --- |
| `propsOf` ne résout `proposeChanges` que via `definitionOfContribution(id).tab` | Pour un id tiers, `proposeChanges` est un **no-op** (`console.warn`) et `errors` vaut toujours `{}` |
| Le contexte d'un composant de configuration reçoit `hass`, `narrow`, `values`, `thermostatId`, `centralValues`, `draft`, plus `language` et `contributionId` | On lit l'état par `hass` + `getEntryEntities`, on écrit par service, on rend nos propres erreurs |
| `draftControls` retourne `undefined` sans session, sans entrée, ou en lecture seule | `draft === undefined` est **le** signal pour désactiver les contrôles |
| `visible` est réévalué à chaque changement de contexte ; une exception **masque** la contribution et émet un `visibility_error` | Le prédicat doit être pur et ne jamais lever |
| `statusOf` renvoie `{kind:"off"}` **avant** d'appeler `status` ; `feature` masque aussi l'élément et la carte d'actions | `feature` est inutilisable pour nous (notre activation est une entité, pas une valeur d'entrée) |
| `hass` d'un composant est un **snapshot** superficiel (`{...hass}`) rafraîchi par un abonnement `history` | Ne jamais comparer l'identité de `hass` pour décider d'un rendu |
| Le sélecteur HA (`SelectOptionDict`) n'a que `{value,label}` — aucun `disabled` par option | L'option `personnalise` ne peut pas être grisée : il faut le retour automatique |
| `save_actions` / `size` / `placement` ne sont appliqués que par le runtime, pas par un schéma serveur | Valeurs à déclarer côté contribution, sans validation serveur |

## Goals / Non-Goals

**Goals:**

- Une seule notion de couverture partagée par le prédicat de visibilité, la
  carte et le widget, pour éviter trois définitions divergentes.
- Un build dont la sortie est committable et servie sans étape manuelle.
- Des erreurs d'écriture visibles dans la carte, puisque le dashboard ne les
  portera pas pour nous.

**Non-Goals:**

- Pas de second mode d'édition hors ligne (file d'attente, brouillon local).
- Pas de retrait ni de remplacement des contributions natives : ce sont des
  changements dans `vtherm_dashboard`, hors de ce dépôt.
- Pas d'enregistrement à chaud si le dashboard est installé après coup
  (voir Décision 2) : un rechargement suffit et c'est ce que dit la spec.

## Decisions

### Décision 1 — Le prédicat de couverture est la présence des cinq entités

Éligible et couvert sont une seule notion : le thermostat est couvert si et
seulement si ses cinq entités existent sur son appareil.

```ts
const KEYS = [
  "auto_start_stop_enable",
  "auto_start_stop_stop_mode",
  "auto_start_stop_level",
  "auto_start_stop_dtmin",
  "auto_start_stop_error_threshold",
];

function covered(hass: Hass, thermostatId: string): boolean {
  try {
    return KEYS.every((key) => getEntryEntities(hass, thermostatId).byKey.has(key));
  } catch {
    return false;
  }
}
```

`byKey` est indexé par `translation_key`, qui vaut exactement le suffixe
d'`unique_id` des cinq entités : c'est le point d'ancrage stable, indépendant des
renommages d'`entity_id`.

*Alternatives écartées.* Lire le flag `is_auto_start_stop_configured` : il est
`false` tant que l'utilisateur n'a rien touché, ce qui masquerait la carte dans le
cas le plus courant. Interroger une API du plugin : il n'y en a pas, et le
navigateur ne peut pas appeler du Python.

*Conséquence assumée.* Le prédicat ne consulte pas l'entrée de configuration ;
il constate le résultat. Si les entités existent, le thermostat est couvert, que
la couverture vienne d'une entrée dédiée ou de la configuration par défaut.

### Décision 2 — Enregistrement conditionné, au démarrage seulement

`after_dependencies: ["vtherm_dashboard"]` (jamais `dependencies`), puis dans
`async_setup` :

```python
if "vtherm_dashboard" in hass.config.components:
    await hass.http.async_register_static_paths(
        [StaticPathConfig(STATIC_URL, str(WWW_DIR), cache_headers=False)]
    )
    register_ui_plugin(
        hass,
        DOMAIN,
        f"{STATIC_URL}/vtherm-auto-start-stop.js?v={version}",
        DASHBOARD_VERSION,
        load_after=[MANAGER_NAME],  # soft link
    )
```

*Alternatives écartées.* Enregistrer inconditionnellement : `register_ui_plugin`
appartient à `vtherm_api`, qui est une exigence dure déjà déclarée, donc il ne
lèverait pas — mais l'enregistrement n'aurait aucun sens sans dashboard et
laisserait une entrée fantôme dans un registre que personne ne lit. Écouter
l'événement de chargement du dashboard pour s'enregistrer à retardement :
complexité réelle pour un cas marginal, et contraire au scénario de spec qui
assume un rechargement.

*Conséquence assumée.* Le chemin statique n'est enregistré que si le dashboard
est présent : sans lui, l'URL du module n'existe pas, ce qui est correct
puisque rien ne la demande.

### Décision 3 — La carte écrit par service, le dashboard ne persiste rien

Chaque contrôle appelle `hass.callService` sur l'entité correspondante. La
contribution déclare `save_actions: "component"` et ne dessine aucun pied
d'action, puisque `draft.dirty` restera faux et qu'Enregistrer/Annuler n'auraient
aucun sens.

Les erreurs de service sont rendues dans un `ha-alert` au-dessus du contrôle
fautif : `missing_configuration`, `invalid_auto_start_stop_option`,
`invalid_auto_start_stop_bound`. C'est nécessaire parce que les entités restaurent
leur valeur précédente avant de propager l'erreur — sans affichage, l'utilisateur
verrait le contrôle revenir en arrière sans explication.

*Alternatives écartées.* Passer par `proposeChanges` : c'est un no-op pour un id
tiers, la valeur serait perdue silencieusement. Utiliser `errors` : toujours `{}`.

### Décision 4 — `personnalise` n'est pas grisé, il revient en arrière

La liste des options est la liste complète des `LEVELS`. Sélectionner
`personnalise` sur un niveau nommé déclenche une écriture que l'entité refuse
sans rien changer ; le sélecteur relit ensuite `current_option`, qui renvoie le
**niveau dérivé** des deux paramètres, et se replace donc de lui-même sur la
valeur d'origine.

*Alternatives écartées.* Griser l'option : impossible, `SelectOptionDict` ne
porte pas de `disabled` (vérifié dans le cœur). Filtrer `personnalise` de la
liste : interdirait le seul moyen d'atteindre un niveau personnalisé, et
contredirait `auto-start-stop-plugin` qui impose la liste complète. Afficher une
aide contextuelle : l'utilisateur a explicitement écarté cette option.

*Conséquence assumée.* L'utilisateur qui choisit « Personnalisé » sans que rien
ne change peut être surpris. Le comportement est celui du plugin, déjà couvert par
`tests/test_select.py` ; la carte ne fait que le refléter fidèlement.

### Décision 5 — Le statut est une fonction, pas un `feature`

```ts
status: ({ hass, thermostatId }) => {
  const entities = getEntryEntities(hass, thermostatId);
  if (entities.byKey.get("auto_start_stop_enable")?.state !== "on") {
    return { kind: "off" };
  }
  const missing = ["auto_start_stop_dtmin", "auto_start_stop_error_threshold"]
    .filter((key) => !isNumeric(entities.byKey.get(key)?.state)).length;
  return missing > 0 ? { kind: "incomplete", missing } : { kind: "complete" };
}
```

`feature` est écarté : il désigne une valeur de l'entrée de configuration du
thermostat, or notre activation est une entité ; de plus le dashboard le teste
**avant** `status` et s'en sert pour ne pas monter l'élément, ce qui rendrait la
carte invisible alors qu'elle doit s'afficher.

La fonction est pure, ne lève jamais, et retourne `undefined` plutôt qu'un statut
inventé si les entités manquent — le dashboard traite alors l'absence de badge.

### Décision 6 — Widget : `thermostat_widget`, taille 1×2, lecture seule

La contribution déclare `size: {columns: 1, rows: 2}`, comme `core_tpi` et
`core_power_energy` : quatre informations (état, erreur/seuil, âge, niveau) ne
tiennent pas confortablement dans une tuile 1×1.

Source de données unique : la section `auto_start_stop_manager` et son booléen
`is_auto_start_stop_configured`. Aucune valeur inventée, aucun appel de service.
Une valeur absente s'affiche « — », jamais `0`.

*Alternatives écartées.* Réutiliser la carte comme widget : les deux contrats
d'accessibilité et de densité diffèrent. Lire les états des entités pour
reconstituer le niveau : le niveau publié est déjà le niveau **dérivé**, et le
recalculer côté navigateur dupliquerait une règle métier.

### Décision 7 — Placement après les contributions natives, dans le groupe Features

Carte : `placement: { after: "core_auto_start_stop.tab.main" }`,
`on_missing: "last"`, `group: CORE_MENU_GROUPS.features`.
Widget : `placement: { after: "core_auto_start_stop.widget.auto_start_stop" }`,
`on_missing: "last"`.

Le placement relatif est une commodité de proximité, pas une dépendance : pour
une installation migrée, les deux contributions natives sont déjà invisibles
(leur gate `use_auto_start_stop_feature` est écrit à `false` par la migration),
donc `on_missing: "last"` fait retomber nos contributions en fin de liste sans
rien casser. Aucune contribution `remove:` ni `replace:` n'est émise.

### Décision 8 — Build Vite en lib, sortie committée dans `www/`

`ui/` devient une racine de build autonome (pas un workspace npm, le dépôt n'en a
pas) : Vite en mode lib, entrée `ui/src/main.ts`, sortie
`custom_components/vtherm_auto_start_stop/www/vtherm-auto-start-stop.js`, format
ES, `@vtherm/dashboard-sdk` laissé externe. Le `?v=` du `js_url` assure le
cache-busting, et `StaticPathConfig(..., cache_headers=False)` évite que le
navigateur serve un ancien bundle.

*Alternatives écartées.* Servir depuis un CDN : le module doit être local, le
résolveur du dashboard rejette une `js_url` non locale hors mode développement.
Un bundle à la demande au démarrage : ajouterait une dépendance Node à
l'exécution de Home Assistant.

## Risks / Trade-offs

- **Le dashboard installé après le plugin n'est pas détecté** → la spec assume un
  rechargement ; à documenter dans les deux README, avec la plus-value du
  dashboard, pour que le cas ne soit pas vécu comme un bug.
- **Le sélecteur de niveau revient en arrière, ce qui peut dérouter** → assumé
  explicitement ; aucune aide contextuelle, conformément à l'arbitrage.
- **`hass` est un snapshot** : un rendu déclenché par comparaison d'identité ne
  se produirait jamais → ne dépendre que des valeurs lues, et rendre à chaque
  mise à jour de propriété.
- **Un prédicat `visible` qui lève masque la contribution et émet un
  `visibility_error`** → `try/catch` renvoyant `false`, jamais d'exception.
- **La carte devient le seul chemin d'édition de la fonctionnalité** une fois les
  contributions natives éteintes → les deux README doivent dire que les entités
  restent utilisables sans dashboard, pour ne pas faire de la carte un point de
  panne unique.
- **Un bundle committé peut diverger des sources** → tâche de vérification en fin
  de plan : rebuild et comparaison avant livraison.

## Migration Plan

1. `manifest.json` : ajout de `after_dependencies` et incrément de version.
2. `__init__.py` : chemin statique et enregistrement conditionnels.
3. `ui/` : sources, catalogue, build ; `www/` committé.
4. README `en` et `fr` : section autonome / plus-value du dashboard.
5. Rechargement de l'intégration. Retour arrière : supprimer `www/` et l'appel
   d'enregistrement ; rien d'autre ne dépend de ce change, aucune entité n'est
   touchée, aucune migration de données n'est nécessaire.

## Open Questions

Aucune. Les trois points laissés ouverts durant l'exploration (taille du widget,
valeurs de placement, mention de la configuration en amorçage dans la carte) sont
tranchés ci-dessus : 1×2, placement après les natives avec repli en fin de liste,
et aucune mention dans la carte — le caractère « amorçage seulement » de la
configuration appartient aux README.
