<p align="left">
  <img src="custom_components/vtherm_auto_start_stop/brand/icon.png" alt="VTherm Auto Start/Stop" width="256" height="256">
</p>

# VTherm Auto Start/Stop

**[Français](README-fr.md) · [English](README.md)** · [Contributeurs (FR)](CONTRIBUTING-fr.md) · [Contributors (EN)](CONTRIBUTING.md)

Un plugin pour [Versatile Thermostat](https://github.com/jmcollin78/versatile_thermostat)
qui arrête automatiquement votre équipement de climatisation une fois que la
pièce a atteint sa consigne, et qui laisse Versatile Thermostat le redémarrer
normalement quand la température s'éloigne à nouveau.

## 🎯 À quoi ça sert ?

Votre équipement (pompe à chaleur, chaudière, climatiseur…) continue de
**fonctionner** jusqu'à ce que la logique de Versatile Thermostat décide du
contraire — même lorsque la pièce est déjà à la consigne. Ce plugin
surveille la température et **demande l'arrêt de l'équipement quand elle est
atteinte**, puis laisse Versatile Thermostat le redémarrer normalement quand la
pièce s'écarte de la consigne.

- **Économies d'énergie** — chaque arrêt automatique évite des minutes inutiles de
  compresseur ou de chaudière.
- **Entièrement automatique** — aucun bouton à presser : c'est le plugin qui
  demande l'arrêt.
- **Vous restez maîtres** — chaque thermostat reçoit un interrupteur *Activer
  auto start/stop* et une sélection *Mode d'arrêt*, directement dans le tableau
  de bord. La carte UI VTherm, inchangée, les pilote exactement comme avant.
- **Une seule configuration globale** couvre tous vos thermostats ; les
  paramètres par thermostat sont optionnels et ne sont jamais nécessaires juste
  pour activer une pièce.
- **Autonome** — l'auto start/stop fonctionne entièrement comme plugin, la
  logique de Versatile Thermostat restant inchangée.

## 🔍 Comment la détection fonctionne-t-elle ? (en termes simples)

Régulièrement, le plugin prend une mesure et se pose une seule question :
**« À combien près la pièce est-elle de la consigne, et depuis combien de temps ? »**

1. **L'écart** — la température actuelle est comparée à la consigne. Si la pièce
   est encore 2 °C sous la consigne, l'écart vaut 2 °C.
2. **Le score** — depuis la mesure précédente, cet écart est multiplié par le
   temps écoulé et ajouté à un **score** courant (l'*erreur accumulée*). Un écart
   qui persiste fait monter le score ; un écart qui disparaît ne le fait pas.
3. **Le verdict** — l'équipement se voit demander un arrêt lorsque le score
   dépasse un **seuil** *et* que la température, projetée avec sa tendance
   actuelle (marge de sécurité de 0,5 °C), a déjà franchi la consigne.
4. **La libération** — lorsque l'écart change de signe (la pièce repart dans
   l'autre sens), le score est divisé par deux plutôt que remis à zéro, pour que
   une petite oscillation ne relance pas toute la détection.
5. **Vos commandes priment** — un changement de preset ou de consigne remet le
   score à zéro immédiatement : vous avez explicitement demandé autre chose,
   donc une détection en instance ne peut pas maintenir la décision précédente.

La rapidité avec laquelle un arrêt est décidé est réglée par le **niveau** : un
niveau fixe la **durée minimale** (`dt_min`, le temps pendant lequel l'écart doit
persister avant tout verdict) et le **seuil de score** à dépasser.

| Niveau        | `dt_min` (minutes) | Seuil de score | Caractère                |
| ------------- | ------------------ | -------------- | ------------------------ |
| Très lent     | 60                 | 20             | Arrête rarement, tard    |
| Lent (défaut) | 30                 | 10             | Équilibré                |
| Moyen         | 15                 | 5              | Modéré                   |
| Rapide        | 7                  | 2              | Arrête vite              |
| Personnalisé  | 5 → 120            | 1 → 50         | Vous choisissez les deux |

Le niveau par défaut est **Lent (30 / 10)**, le comportement de
l'ancienne fonctionnalité du core.

> Avec le niveau **Personnalisé**, vous choisissez vous-même les deux valeurs :
> une durée minimale entre **5 et 120 minutes** et un seuil entre **1 et 50**
> (pas de 0,5). Les deux champs sont **toujours affichés** dans le formulaire de
> configuration, quel que soit le niveau courant. Ils ne s'appliquent que quand
> le niveau vaut *Personnalisé* — un niveau nommé utilise son tableau statique —
> et les valeurs sont sauvegardées dans l'entrée pour ne pas avoir à les
> ressaisir en revenant à *Personnalisé*.

## 📋 Thermostats pris en charge

- Seuls les thermostats **`over_climate`** (un Versatile Thermostat pilotant un
  équipement clim) sont éligibles.
- **Les thermostats à régulation par vanne ne sont pas pris en charge** — la
  même restriction que la fonctionnalité du core, conservée volontairement pour
  que la migration soit une simple mainlevée.

## 📦 Installation

**Prérequis**

- Home Assistant **2026.10** ou plus récent.
- Versatile Thermostat **11.x ou une version ultérieure**, avec la prise en
  charge de la **délégation externe auto start/stop**.

**Option A — HACS**

1. Ajoutez ce dépôt comme intégration personnalisée dans HACS (via la *Marketplace*
   ou à partir de l'URL du dépôt).
2. Redémarrez Home Assistant.
3. Allez dans **Paramètres → Appareils et services** et ajoutez
   **VTherm Auto Start/Stop**.

**Option B — Manuelle**

1. Copiez le dossier `custom_components/vtherm_auto_start_stop` dans le
   répertoire `config/custom_components/` de Home Assistant.
2. Redémarrez Home Assistant.
3. Allez dans **Paramètres → Appareils et services** et ajoutez
   **VTherm Auto Start/Stop**.

## ⚙️ Configuration

### 🌍 La configuration globale (la seule obligatoire)

La première fois que vous ajoutez l'intégration, vous configurez les
**paramètres globaux** :

- **Niveau** — le niveau de détection appliqué à tous les thermostats
  (tableau ci-dessus).
- **Activation initiale** et **mode d'arrêt initial** — des valeurs par défaut
  utilisées **uniquement** tant que les contrôles d'un thermostat n'ont pas
  d'état sauvegardé (un thermostat nouveau). Une fois qu'un contrôle a un état
  sauvegardé, modifier ces valeurs par défaut ne le réinitialise jamais, même
  s'il n'a jamais été touché à la main.

Chaque thermostat éligible reçoit automatiquement sa propre paire de contrôles :

- **Activer auto start/stop** (interrupteur) — active ou désactive la détection
  pour ce thermostat uniquement, sans toucher à son mode d'arrêt sauvegardé.
- **Mode d'arrêt** (sélection) — le mode HVAC appliqué quand le plugin demande
  un arrêt :

| Option            | Comportement à l'arrêt automatique      | Disponibilité |
| ----------------- | --------------------------------------- | ------------- |
| Off `off`         | L'équipement est mis hors tension       | Toujours      |
| Ventilation       | L'équipement passe en ventilation       | Si supporté   |
| Déshumidification | L'équipement passe en déshumidification | Si supporté   |

> **`Off` est un mode d'arrêt, pas un moyen de désactiver la fonctionnalité.**
> Désactiver ou activer la détection est le seul rôle de l'interrupteur ;
> choisir `Off` ne dit que *comment* l'équipement est arrêté. Choisir un mode
> d'arrêt n'active ni ne désactive la détection.

Tous ces états survivent aux rechargements et redémarrages. Modifier un contrôle
ne crée jamais d'entrée de configuration et ne modifie jamais les paramètres
globaux.

### 🎛️ Les paramètres par thermostat (entrées dédiées optionnelles)

Si un thermostat a besoin de **paramètres de détection** différents — par
exemple une pièce qui monte vite et ne devrait pas être arrêtée précipitamment —
ajoutez une autre entrée de configuration :

1. Ajoutez **VTherm Auto Start/Stop** une nouvelle fois depuis *Appareils et
   services*.
2. Sélectionnez le thermostat.
3. Choisissez son niveau (et ses valeurs Personnelles, si besoin).

Les entrées dédiées ne modifient **que les paramètres** : l'activation et le
mode d'arrêt restent toujours sur les contrôles d'entité (aucune entrée dédiée
n'est jamais nécessaire pour ça). Les paramètres non définis dans l'entrée
dédiée héritent de l'entrée globale, puis des valeurs par défaut du plugin.

### 🗑️ Supprimer des entrées

- Supprimer une entrée **dédiée** restaure l'héritage des paramètres ; les
  contrôles, l'activation et le mode d'arrêt du thermostat sont intacts.
- Supprimer l'entrée **globale** retire les contrôles de tous les thermostats
  qui n'ont pas d'entrée dédiée ; ceux qui en ont continuent à fonctionner, les
  paramètres manquants basculant sur les valeurs par défaut du plugin.

## 🔄 Migration depuis la fonctionnalité du core

Si vos thermostats utilisaient déjà l'auto start/stop intégré :

- Avec les versions coordonnées du core et du plugin installées, un rechargement
  passe la main au plugin : le core efface son drapeau de fonctionnalité
  historique, supprime l'ancien interrupteur et la sélection, et le plugin
  recrée les contrôles **sous leurs anciens identifiants d'entité exacts** —
  tableaux de bord, cartes et automatisations continuent de fonctionner sans
  changement.
- Lorsque vous créez une entrée dédiée, son niveau est **initialisé depuis le
  niveau historique du core** quand celui-ci est disponible ; une entrée dédiée
  existante n'est jamais écrasée.
- Supprimer le plugin ne **réactive pas silencieusement** l'ancienne
  fonctionnalité du core — réactivez-la via Versatile Thermostat si vous la
  voulez de retour.

## ❓ Questions fréquentes

**J'ai désactivé la fonctionnalité sur un thermostat — pourquoi les contrôles
et les attributs s'affichent-ils encore ?**
Désactiver est un état sauvegardé, pas une désinstallation : le thermostat
conserve son score (gelé), son mode d'arrêt et ses deux contrôles, de sorte que
la réactivation est immédiate. En mode désactivé, la détection n'accumule plus
et ne demande aucun arrêt.

**Puis-je activer la fonctionnalité pour un seul thermostat ?**
Oui — configurez les paramètres globaux avec *activation initiale* désactivée,
puis retournez l'interrupteur seulement sur le(s) thermostat(s) concerné(s).
Aucune entrée de configuration supplémentaire n'est créée.

**Mon thermostat à vanne n'apparaît pas dans le sélecteur.**
C'est volontaire : les thermostats à régulation par vanne restent exclus,
exactement comme avec la fonctionnalité du core.

## 🤝 Contribuer

Voir [CONTRIBUTING-fr.md](CONTRIBUTING-fr.md) / [CONTRIBUTING.md](CONTRIBUTING.md)
pour la conception, le workflow OpenSpec obligatoire et les interactions avec
le core Versatile Thermostat.

> **Note :** Ce plugin remplace la fonction équivalente d'auto start/stop du
> core Versatile Thermostat, qui sera **totalement supprimée en 2027**.
