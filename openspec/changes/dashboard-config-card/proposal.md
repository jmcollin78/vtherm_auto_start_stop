# Proposal

## Why

`vtherm_dashboard` embarque une carte native `core_auto_start_stop` qui lit les
attributs `auto_start_stop_manager.*` publiés par le thermostat. Une fois la
décision déléguée au plugin (`auto-start-stop-delegation`), cette carte cesse
d'être utilisable, pour trois raisons indépendantes :

- sa visibilité exige `use_auto_start_stop_feature === true`, or la migration du
  core force ce flag à `false` — l'onglet et le widget natifs disparaissent
  exactement quand le plugin prend la main ;
- elle écrit dans l'entrée du thermostat (étape `STEP_AUTO_START_STOP`), qui est
  précisément devenue inerte sous délégation : les valeurs y sont sans effet ;
- son widget est en lecture seule par construction, et n'affiche pas le niveau
  dérivé des deux paramètres.

Le blocage qui justifiait de garder ce change en réserve est levé :
`parameters-as-entities` est archivé, donc les cinq paramètres existent désormais
comme entités sur l'appareil du thermostat. Une contribution du plugin lui-même
peut donc les afficher **et** les modifier.

## What Changes

- Le plugin devient un **UI plugin** au sens de `vtherm_dashboard` : un module ES
  servi sous `/vtherm_auto_start_stop_static/`, enregistré auprès de `vtherm_api`
  par `register_ui_plugin(...)`.
- Le plugin **reste pleinement fonctionnel sans le dashboard**. Le dashboard est
  une dépendance d'ordre de démarrage (`after_dependencies`), jamais une
  dépendance dure ; aucune erreur n'est levée quand il est absent, la carte est
  simplement inutilisée. L'autonomie et la plus-value du dashboard sont
  documentées dans `README.md` et `README-fr.md`.
- Nouvelle **carte de configuration** (`thermostat_config`) dans le menu du
  thermostat, avec les cinq contrôles, en **écriture immédiate** par
  `hass.callService` sur les entités du thermostat couvert.
- Nouveau **widget de synthèse** (`thermostat_widget`) affichant l'état de
  détection, l'erreur accumulée face au seuil, l'âge du dernier basculement et le
  **niveau dérivé** — ce dernier étant l'écart fonctionnel avec le widget natif.
- Nouveau **statut de section** dans le menu : `off` / `complete` /
  `incomplete{missing}`, sans état `inherited`.
- Les contributions natives `core_auto_start_stop` sont **laissées intactes** :
  aucune contribution `remove:` ni `replace:`. Aucune modification n'est
  demandée au dépôt `vtherm_dashboard`.
- **BREAKING** — aucun. Ce change n'ajoute que des contributions et ne retire ni
  n'altère aucune entité existante.

## Capabilities

### New Capabilities

- `auto-start-stop-dashboard`: le plugin se présente comme UI plugin de VTherm
  Dashboard. Couvre l'enregistrement conditionné à la présence du dashboard, le
  mode autonome sans dashboard, la visibilité des contributions indexée sur la
  présence des entités, le statut de section, la carte de configuration en
  écriture immédiate, et le widget de synthèse en lecture seule.

### Modified Capabilities

Aucune. Le contrat des cinq entités (`auto-start-stop-plugin`) et les règles de
délégation (`auto-start-stop-delegation`) sont inchangés : ce change les consomme
tels quels. Aucun prérequis du plugin n'est modifié non plus, puisque le dashboard
reste facultatif.

## Décisions actées

Neuf arbitrages ont été rendus durant l'exploration. Ils fixent le périmètre ;
leur mise en oeuvre appartient à `design.md`.

| # | Sujet | Décision |
|---|-------|----------|
| 1 | Dépendance dashboard | `after_dependencies`, jamais `dependencies`. Enregistrement de l'UI plugin seulement si le dashboard est chargé. Aucune erreur sinon. Autonomie documentée dans les deux README. |
| 2 | Visibilité de la carte | Éligible et couvert sont une seule notion : les cinq entités existent. La carte s'affiche dès que le thermostat est couvert, sans attendre une configuration utilisateur. |
| 3 | Modèle d'écriture | Écriture immédiate, contrôle par contrôle, par `hass.callService`. Pas de brouillon, pas de bouton Enregistrer. |
| 4 | Niveau `personnalise` | La liste complète des niveaux est offerte. Sélectionner `personnalise` sur un niveau nommé ne change rien : l'écriture est refusée, le niveau dérivé reste inchangé, et le sélecteur revient de lui-même sur sa valeur courante. Pas d'aide contextuelle, pas d'option grisée. |
| 5 | Widget | Un widget de synthèse est créé, en plus de la carte. |
| 6 | Statut de section | `off` / `complete` / `incomplete{missing}`. Pas d'état `inherited`. |
| 7 | Contributions natives | Laissées intactes. Aucune contribution `remove:` ni `replace:`, aucune modification du dashboard. |
| 8 | Actions de la carte | `save_actions: "component"` : la carte dessine elle-même l'absence de pied d'actions, puisqu'elle n'édite aucun brouillon. |
| 9 | Traductions | Catalogues `en` et `fr` fournis par le plugin ; la langue vient du dashboard. |

La décision 7 **annule** une orientation du change archivé `parameters-as-entities`,
qui confiait à ce change le retrait des contributions natives devenues legacy. Ce
retrait n'a pas lieu d'être : les deux contributions natives sont déjà gardées par
`use_auto_start_stop_feature`, que la migration du core écrit à `false`. Elle
s'éteignent donc d'elles-mêmes, et le plugin n'a rien à défaire.

## Impact

**Dépôt `vtherm_auto_start_stop`**

- `custom_components/vtherm_auto_start_stop/manifest.json` —
  `after_dependencies: ["vtherm_dashboard"]`.
- `custom_components/vtherm_auto_start_stop/__init__.py` — enregistrement du
  chemin statique et de l'UI plugin, conditionné à la présence du dashboard.
- `custom_components/vtherm_auto_start_stop/www/` — nouveau répertoire, artefact
  de build (module ES compilé).
- `ui/` — nouvelle racine de build TypeScript/Vite : sources, catalogue de
  traductions, tests. Consomme `@vtherm/dashboard-sdk`.
- `version` du plugin à incrémenter.
- `README.md` et `README-fr.md` — section « autonome / plus-value du dashboard ».

**Dépôt `vtherm_dashboard`** — aucune écriture. Les contributions natives
`core_auto_start_stop` restent en place et s'éteignent d'elles-mêmes par leur
gate `use_auto_start_stop_feature`.

**Dépendances** — `@vtherm/dashboard-sdk` (≈ `0.1.0-beta4`), Node ≥ 24, build
Vite vers `www/`. Côté Python, `vtherm_api>=0.13.1` est déjà déclaré et suffit.

**Prérequis** — satisfait : `parameters-as-entities` est archivé, les cinq
entités existent.
