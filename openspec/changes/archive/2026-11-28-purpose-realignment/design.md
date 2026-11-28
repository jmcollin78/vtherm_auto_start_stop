# Design

## Contexte

`parameters-as-entities` a déplacé les paramètres de détection de l'entrée de
configuration vers des entités. La spec principale a été synchronisée : six
exigences ajoutées, cinq réécrites, six retirées. La section `## Purpose` est la
seule zone restée en arrière, parce que le contrat de synchronisation OpenSpec
interdit de la réécrire pendant une fusion — elle est copiée verbatim depuis le
delta pour une nouvelle capacité, et laissée intacte pour une capacité existante.

## Ce que le nouveau Purpose doit dire

Trois faits, et rien d'autre :

1. **Ce qui définit la couverture** : une entrée globale, ou une entrée dédiée
   par thermostat. Une entrée ne porte plus de paramètres de détection.
2. **Ce que le plugin expose** : cinq contrôles par thermostat couvert —
   activation, mode d'arrêt, préréglage de niveau, durée minimale, seuil d'erreur.
3. **Ce que le manager décide** : il accumule la déviation entre la température
   courante et la consigne, et demande l'arrêt du thermostat quand elle reste
   au-delà du seuil plus longtemps que la durée minimale.

Le niveau est une **étiquette dérivée** de la paire (durée, seuil) : c'est le
point le plus important à conserver, parce qu'il explique pourquoi le préréglage
n'est pas un stockage.

## Ce que le nouveau Purpose ne doit pas dire

- « layered », « cascade », « plugin defaults → global instance → dedicated
  overrides » : ce mécanisme est supprimé.
- Toute liste de niveaux ou de bornes : elles vivent dans les exigences, et les
  citer dans le résumé crée une seconde source à maintenir.
- Le vocabulaire de migration : c'est un fait historique, déjà couvert par
  « Migration from the core configuration ».

## Forme

Un paragraphe, à la manière des deux autres specs du dépôt
(`auto-start-stop-delegation`, `thermostat-runtime-api`), qui tiennent chacune en
deux à quatre phrases. Pas de liste, pas de tableau : le résumé reste lisible
d'un coup d'œil.

## Risque et réversibilité

Le fichier est suivi par git. La réécriture se vérifie en relisant les dix
premières lignes, et se défait par `git checkout --
openspec/specs/auto-start-stop-plugin/spec.md`. Aucun autre fichier n'est touché.
