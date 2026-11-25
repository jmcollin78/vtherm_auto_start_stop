# Contribuer à VTherm Auto Start/Stop

**[Contributeurs (FR)](CONTRIBUTING-fr.md) · [Contributors (EN)](CONTRIBUTING.md)** ·
[Documentation utilisateur (FR)](README-fr.md) · [User documentation (EN)](README.md)

Ce dépôt est **à la fois** l'hub OpenSpec et l'intégration complète :
`custom_components/vtherm_auto_start_stop/` (le code) et `tests/` vivent ici, et
`openspec/` contient les spécifications, les propositions de changement et
l'archive.

> **À lire dans cet ordre :** 1. Arborescence du dépôt → 2. Comment le plugin
> dialogue avec le core → 3. Le workflow OpenSpec obligatoire → 4. Les
> principes de conception → 5. Les règles de code et de test → 6. Documenter.

## 1. Arborescence du dépôt

```
├── custom_components/vtherm_auto_start_stop/   # l'intégration
│   ├── __init__.py      # setup : init global, async_remove, orchestration rechargement
│   ├── const.py         # domaine, niveaux, clés de config, valeurs par défaut
│   ├── models.py        # dataclasses frozen/slots (entrées, paramètres, snapshot)
│   ├── algorithm.py     # l'algorithme de détection pur (aucun import Home Assistant)
│   ├── manager.py       # manager de détection : snapshots, état, paramètres par niveau
│   ├── registry.py      # registre des thermostats + coordination rechargement/inscription
│   ├── factory.py       # éligibilité (supports()) + création des contrôles
│   ├── config_flow.py   # le (seul) flux de configuration, global et dédié
│   ├── select.py        # l'entité sélection du mode d'arrêt
│   ├── entity.py        # base commune aux deux entités de contrôle
│   ├── switch.py        # l'entité interrupteur Activer auto start/stop
│   ├── strings.json     + translations/{en,fr}.json
│   └── manifest.json
├── tests/                           # suite pytest (pure, sans Home Assistant)
└── openspec/                        # l'hub de spécification (voir §3)
    ├── specs/                     # specs de capacités actuelles (source de vérité)
    ├── changes/archive/           # changements terminés et archivés (historique)
    └── changes/<change>/          # changements en cours (delta + tâches)
```

Trois des quatre specs de capacités actuelles vivent dans `openspec/specs/` :
`auto-start-stop-plugin`, `auto-start-stop-delegation` et
`thermostat-runtime-api`. Considérez **`openspec/specs/` comme la source de
vérité unique du comportement** ; `openspec/changes/` ne *décrit* que des
deltas.

## 2. Comment le plugin dialogue avec le core

Le plugin **ne patche jamais ni ne sous-classe** le core Versatile Thermostat.
Tout le contrat passe par une API de délégation fine exposée par le package
`vtherm_api` (PyPI, pinné dans `manifest.json`), implémentée par le core.

```
                    ┌────────────────────────────────────────────┐
                    │  Core Versatile Thermostat (jmcollin78)    │
                    │                                            │
   enregistre ────► │  FeatureManager  ◄──►  InterfaceThermostat │
                    │  (FeatureInstance   │     Runtime          │
                    │   par thermostat)   │                     │
                    └──────────────┬─────┴───────────────────────┘
                                   │  vtherm_api (PyPI, pinné)
                    ┌──────────────▼─────────────────────────────┐
                    │  vtherm_auto_start_stop (ce plugin)        │
                    │  register_feature_manager / async_start    │
                    │  InterfaceVThermAutoStartStop (adaptateur) │
                    └────────────────────────────────────────────┘
```

Ce que le plugin **consomme** (core → plugin) :

- `InterfaceThermostatRuntime` — données du snapshot courant : `current_temp`,
  `target_temp`, `requested_hvac_mode`, `current_hvac_mode`.
- `has_valve_regulation: bool` — pilote l'exclusion des vannes (D14).
- `vtherm_hvac_modes: tuple` — modes disponibles, pilote la sélection du mode
  d'arrêt.
- `async_request_state_refresh()` — le rafraîchissement synchrone unique que
  le détecteur effectue sur un changement de preset/consigne (D16) ; seul le
  core peut l'appeler, le plugin ne le planifie jamais.

Ce que le plugin **injecte** (plugin → core, via
`InterfaceVThermAutoStartStop`) :

- `is_active()` — l'état de l'interrupteur ; le core doit le consulter avant de
  cumuler ou de décider.
- `get_stop_mode()` — la valeur du mode d'arrêt sélectionné.
- `apply_stop_mode(mode) -> bool` — un appel **synchrone en requête seule** :
  le core réalise le changement de mode HVAC (ou la mise hors tension quand la
  valeur est un mode `off`) dans le même tour de boucle, ne le planifie
  jamais, n'échoue jamais bruyamment.
- `has_accumulated_error` — lu au rechargement (voir §4, persistance).

Les deux capacités qui codifient ce contrat vivent en specs :
`auto-start-stop-delegation` (le côté core générique) et
`thermostat-runtime-api` (le côté plugin concret). **Tout changement de la
surface de l'API doit être proposé via un changement OpenSpec** qui met à jour
ces specs, et livré en triple coordonnée (core + `vtherm_api` + ce plugin).

### Éligibilité et legacy `none` (invariants I2–I6)

`factory.supports()` — et le sélecteur du flux de configuration dédié —
**ne propose que** un thermostat `over_climate` **sans régulation par vanne**.
L'entité auto start/stop historique du core (quand
`legacy_auto_start_stop_entity` est non nul) est toujours proposée en item
supplémentaire, pour que la voie de migration ait toujours une entrée dédiée à
seed.

Le niveau historique `none` **n'est plus sélectionnable** ; toute valeur
stockée qui lit encore `none` est normalisée vers le niveau par défaut (Lent)
au chargement. `none` n'a jamais été un mode d'arrêt, donc aucune migration
d'état n'est nécessaire. Le code peut conserver une constante historique pour
la rétrocompatibilité, mais elle ne doit jamais être ni sélectionnée ni écrite
par l'interface.

## 3. Le workflow OpenSpec obligatoire ⚠️

**Tout changement de comportement de ce dépôt doit passer par OpenSpec.** C'est
une règle dure pour cet hub, pas une politesse : la sémantique du plugin est
seulement significative face au contrat de délégation du core, et les deux
côtés évoluent en triple coordonnée. Passer le workflow ou commiter du
comportement sans spec d'abord rendrait les contributions futures impossibles
à vérifier.

### Le workflow

```
new ──► propose ──► apply ──► sync ──► archive
 │         │           │         │        │
 │         │           │         │        └─► openspec archive <change>
 │         │           │         └─► delta mergé dans openspec/specs/
 │         │           └─► implémentation + tests
 │         └─► delta spec + proposal + design + tasks
 └─► openspec new <change>  (crée openspec/changes/<change>/)
```

Pour chaque changement vous écrirez, dans `openspec/changes/<change>/` :

- `proposal.md` — `## Why`, `## What Changes` (puces simples),
  `## Capabilities` (`### New Capabilities` / `### Modified Capabilities`),
  `## Impact` (fichiers, version de `vtherm_api`, compatibilité core,
  migration).
- `design.md` — les décisions **`D1`, `D2`, …** avec justification et
  compromis.
- `specs/<capability>/spec.md` — le delta (voir le format ci-dessous).
- `tasks.md` — listes de tâches (`- [ ]`), groupées par zone.

### Écrire un delta valide

C'est la partie sur laquelle le validateur est strict. Faites-le bien dès le
départ :

- **En-tête :** `# <capability> Specification` ; puis `## Purpose` (lorsqu'on
  ajoute à la capacité pour la première fois, ou qu'on la réénonce) et
  `## Requirements`.
- Pour une demande **nouvelle** : une section `## ADDED Requirements` ; pour
  une modification d'une existante : une section `## MODIFIED Requirements` —
  et la demande *entière* est écrite, pas juste le diff. Un même document de
  delta peut avoir **les deux** sections, appliquées à la spec principale
  comme une merge transactionnelle unique.
- **Les titres de demande** sont `### Requirement: <nom court>` et le corps
  doit utiliser un **langage normatif** — `must`, `shall`, `must not` — avec le
  *pourquoi* inclus dans le corps de la demande.
- **Les scénarios** sont `#### Scenario: <nom>` (exactement quatre croisillons),
  chacun avec un corps `WHEN … THEN …` (facultativement `AND …`). **Au moins
  un** scénario par demande, et chaque scénario doit rester cohérent avec le
  corps de la demande (le validateur le vérifie en `--strict`).
- **Descriptions ≤ 500 caractères.** Les longs paragraphes dans le corps d'une
  demande feront échouer `openspec validate <change> --strict`.
- Ne **réénoncez pas** le delta sous forme de puces dans `design.md` puis
  *encore* dans la spec — la spec est la source de vérité, le design est la
  justification.

### Les commandes (toujours via `rtk`)

```bash
rtk openspec new <change>                 # scaffolde openspec/changes/<change>/
rtk openspec status --change <name> --json
rtk openspec validate --all --strict      # la porte : 0 échec attendu
rtk openspec instructions specs --change <name> --json
rtk openspec instructions archive --change <name> --json
rtk openspec archive <change>             # merge delta → specs/ + passage en archive/
```

**La porte est `rtk openspec validate --all --strict` et elle doit se terminer
par `X/0` (X passant, 0 échec) avant qu'un PR soit merged.** Un piège connu :
un dossier résiduel `openspec/changes/<name>/` qui ne contient qu'un
`tasks.md` (dupliqué) sans `proposal.md` fera signaler ce changement par le
validateur même s'il est déjà archivé — si vous voyez un changement « fantôme »
dans la sortie de validation, `diff`ez son `tasks.md` contre
`openspec/changes/archive/<date>-<name>/tasks.md` et **supprimez le résidu**
(c'est un doublon de la copie archivée, pas un changement en cours).

**Ne modifiez jamais `openspec/specs/` directement.** La spec principale est
toujours le résultat d'un changement archivé ; la modifier à la main
desynchronise l'historique. Si une spec est fausse, déposez un changement avec
une demande MODIFIED qui la corrige.

### Exemple : un changement passé

`2026-11-25-vtherm-auto-start-stop-personnalise` montre la forme complète d'un
changement de fonctionnalité : proposition, six décisions de design (D1–D6), un
delta avec 10 demandes ADDED et 2 demandes MODIFIED, et 6 groupes de tâches. Il
est archivé, donc son delta a été mergé dans
`openspec/specs/auto-start-stop-plugin/spec.md`. Lisez-le avant d'écrire votre
première proposition.

## 4. Principes de conception

Les invariants (I1–I9) et la liste de décisions (D1–D16) du changement
originel sont la référence ; ils restent normatifs. Ceux qui mordent le plus
souvent :

1. **Détection pure.** `algorithm.py` n'a **aucun import Home Assistant**. Le
   détecteur ne parle jamais à un objet thermostat : il reçoit un snapshot
   immuable (un dataclass frozen) et produit une décision. Tout comportement
   spécifique HA (entités, entrées de config, rafraîchissement) vit hors de ce
   module. *Corollaire :* l'algorithme est trivialement unit-testable — voir
   les règles de test en §5.
2. **Aucun rafraîchissement planifié.** Quand le preset ou la consigne change,
   le manager (a) réinitialise l'algorithme, (b) **appelle
   synchronement** `async_request_state_refresh()` sur l'interface runtime et
   reconstruit le snapshot — il ne doit *jamais* planifier un callback,
   `schedule_update_ha`, ni un callback de souscription d'état. C'est pour ça
   que D16 existe, et pourquoi le core est le seul côté autorisé à planifier
   quoi que ce soit.
3. **La persistance est par design.** L'erreur accumulée, le niveau et l'état
   par thermostat (`_last_state`) survivent aux rechargements ; le manager
   reconstruit `_last_state` et `_last_request_state` depuis
   `InterfaceThermostatRuntime` et le snapshot persisté
   `has_accumulated_error` à l'init. `has_accumulated_error` est *lu* au
   rechargement, jamais écrit par le plugin après l'init.
4. **Le legacy `none` est normalisé, pas supprimé.** Toute valeur stockée
   `none` résolue transparentement vers le niveau par défaut ; aucune
   migration d'état stocké n'est jamais nécessaire parce que `none` n'a jamais
   été un mode d'arrêt.
5. **L'éligibilité a une source de vérité unique.** `factory.supports()` et le
   sélecteur du flux de configuration partagent la même règle
   (`over_climate and not has_valve_regulation` + offre
   legacy-entity). Si vous changez l'un, vous changez l'autre, ou vous changez
   d'abord la spécification de la capacité (et les tests).
6. **L'exclusion par vanne est absolue.** C'est une décision de périmètre
   *normative* (D14) héritée du core, *pas* un fossé à « corriger » en
   sous-produit. Lever cette restriction uniquement via un changement de spec
   qui le dit explicitement.

## 5. Règles de code et de test

**Runtime** — Home Assistant ≥ 2026.10 ; `vtherm_api >= 0.13.1` est déclarée
dans `manifest.json` et pinnée dans `requirements_test.txt`. **Ne importez
jamais** le core comme package Python ici ; l'unique import est `vtherm_api`.

**Algorithme** — le détecteur doit être sûr sur les écarts de temps, les
changements de mode (`off` short-circuite), les changements de
preset/consigne (reset total) et les changements de signe (diviser par deux).
Les constantes `CYCLE_SEC`, `MIN_CYCLE_RATIO`, `TEMP_HYSTERESIS` sont
normatives ; les modifier est un changement de comportement → changement
OpenSpec d'abord.

**Test**

```bash
python -m pytest tests/                # la suite complète (pure, sans HA requis)
```

- Les tests sont **purs** (pas de `pytest-homeassistant-custom-component`, pas
  de fixtures Home Assistant) : `algorithm.py`, `models.py` et `registry.py`
  sont testés comme du Python pur. `manager.py` est testé avec des *interfaces
  runtime factices* (quelques dizaines de lignes, voir
  `tests/test_manager.py`).
- Nouveau comportement → nouveau test dans le
  `tests/test_<module>.py` correspondant. Nommez les tests après la
  demande/scénario qu'ils encodent quand c'est faisable
  (ex. `test_none_level_normalised_to_slow`).
- `tests/` doit rester exécutable **sans installation Home Assistant** ; le
  `setup` de l'intégration elle-même n'est pas exercé ici.

**Lint / style** — calquez le code existant (pas de config de formateur lourde
dans le dépôt ; gardez les imports en haut du module, `from __future__ import
annotations` dans les nouveaux modules, dataclasses frozen/slots pour les
nouveaux modèles d'état).

## 6. Documenter

- **Docs utilisateur / installateur** → `README.md` (anglais) + `README-fr.md`
  (français). Gardez les deux fichiers synchronisés ; la navigation d'en-tête
  doit cross-linker la paire.
- **Docs contributeurs** → ce fichier et son jumeau français. Tout changement
  du workflow OpenSpec décrit ici doit correspondre à ce que
  `openspec/changes/` utilise réellement.
- **Langue :** fichier sans extension = anglais (défaut) ; suffixe `-fr` =
  français. N'ajoutez pas une troisième langue tant que le dépôt n'en gagne
  pas une.
- **Ne copiez jamais** les corps `Requirement`/`Scenario` de la spec OpenSpec
  dans le README : le README explique *ce que voit l'utilisateur* ; la spec
  définit *ce que le système doit faire*.
