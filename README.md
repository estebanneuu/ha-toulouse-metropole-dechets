# Toulouse Métropole Déchets pour Home Assistant

[![Validation](https://github.com/estebanneuu/ha-toulouse-metropole-dechets/actions/workflows/validate.yml/badge.svg)](https://github.com/estebanneuu/ha-toulouse-metropole-dechets/actions/workflows/validate.yml)
[![Version](https://img.shields.io/github/v/release/estebanneuu/ha-toulouse-metropole-dechets)](https://github.com/estebanneuu/ha-toulouse-metropole-dechets/releases)
[![Licence MIT](https://img.shields.io/badge/licence-MIT-blue.svg)](LICENSE)

Intégration personnalisée **0.1.1** : une adresse configurable, sept types de déchets, un calendrier, un capteur de prochaine date et un capteur de statut pour chacun. Plusieurs adresses peuvent être ajoutées.

L’intégration est indépendante de Toulouse Métropole. Elle utilise les données publiques officielles et vise les 37 communes. La couverture effective dépend des tronçons et secteurs publiés pour l’adresse. Cette version est prévue pour **Home Assistant 2026.11 ou ultérieur**, avec validation sous **2026.11.2**.

## Collectes prises en charge

| Type | Fonctionnement |
| --- | --- |
| Ordures ménagères | Recherche des tronçons à proximité, confirmation de la tournée, dates calculées à partir des jours publiés. |
| Emballages et papiers | Même fonctionnement, avec semaines ISO paires et impaires. |
| Végétaux — abonnement saisonnier gratuit | Dates exactes publiées par secteur sur la carte officielle. Choisir ce mode seulement si vous êtes abonné. |
| Végétaux — abonnement annuel payant | Règle de secteur + calendrier annuel officiel + dates saisonnières. **Exceptions validées uniquement pour 2026** ; aucune extrapolation des collectes payantes en 2027. |
| Encombrants | Sur rendez-vous : saisir la ou les dates confirmées dans les options. L’intégration ne réserve aucun rendez-vous. |
| Verre | Statut apport volontaire par défaut ; possibilité de saisir un calendrier local confirmé si votre cas le nécessite. |
| Déchets alimentaires | Statut apport volontaire / compostage par défaut. Vérifier le dispositif effectivement proposé à votre adresse. |
| Textiles | Statut apport volontaire par défaut. |

Tous les types peuvent recevoir des dates manuelles. Un flux en apport volontaire ou sur rendez-vous sans date renseignée reste sans événement. La localisation des bornes, les heures d’ouverture des déchèteries et les campagnes ponctuelles de dépôt des sapins ne font pas partie de cette version.

## Installation

### Avec HACS

[![Ouvrir le dépôt dans HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=estebanneuu&repository=ha-toulouse-metropole-dechets&category=integration)

1. Ouvrir **HACS → menu ⋮ → Dépôts personnalisés**.
2. Ajouter `https://github.com/estebanneuu/ha-toulouse-metropole-dechets` avec le type **Intégration**.
3. Rechercher **Toulouse Métropole Déchets**, télécharger la dernière version puis redémarrer Home Assistant.
4. Ouvrir **Paramètres → Appareils et services → Ajouter une intégration → Toulouse Métropole Déchets**.
5. Suivre la configuration par adresse et confirmer vos tournées.

Le dépôt fonctionne comme dépôt HACS personnalisé. Son ajout au catalogue par défaut nécessite une validation séparée des mainteneurs HACS ; publier ce dépôt ne vaut pas acceptation dans le catalogue.

### Installation manuelle

1. Extraire l’archive et copier le dossier `custom_components/toulouse_metropole_dechets` dans le dossier `config/custom_components` de Home Assistant.
2. Vérifier le chemin final : `config/custom_components/toulouse_metropole_dechets/manifest.json`.
3. Redémarrer Home Assistant.
4. Ouvrir **Paramètres → Appareils et services → Ajouter une intégration → Toulouse Métropole Déchets**.
5. Saisir une adresse complète, sélectionner le résultat IGN puis confirmer les tournées OM et tri correspondant à votre rue. Comparer avec le calendrier de votre commune. Choisir ensuite votre abonnement végétaux ou passer cette étape.

L’archive des sources est disponible dans les [releases GitHub](https://github.com/estebanneuu/ha-toulouse-metropole-dechets/releases). Pour une mise à jour manuelle, remplacer le dossier de l’intégration puis redémarrer Home Assistant.

## Configuration et corrections

Dans les options de l’intégration, choisir le type de déchets puis son mode :

- **Tournée hebdomadaire** : `Lundi`, `Le lundi et jeudi`, `Mercredi semaine impaire`, `7 jours / 7`…
- **Dates confirmées saisies** : `2026-11-24, 2026-12-08`. Utiliser ce mode pour un rendez-vous encombrants confirmé.
- **Apport volontaire**, **Sur rendez-vous** ou **Calendrier non renseigné** : aucun jour de passage produit.

Les champs **Dates à retirer** et **Dates supplémentaires / rattrapages** s’appliquent aux dates calculées et saisies. Une exclusion explicite l’emporte sur un ajout. Si le calendrier officiel végétaux est activé, il remplace la liste des dates, tout en respectant les ajouts et exclusions. Pour utiliser un calendrier végétaux personnel, désactiver ce calendrier officiel dans les options.

Les tournées OpenData sélectionnées sont revérifiées toutes les 12 heures. Si leur règle change, le calendrier suit la nouvelle règle. Une règle modifiée manuellement cesse de suivre la tournée officielle. Pour choisir une autre adresse ou réassocier une tournée, supprimer l’entrée de l’intégration puis l’ajouter à nouveau.

Les dates sont recalculées à minuit dans le fuseau configuré dans Home Assistant, sans requête réseau supplémentaire. Utiliser normalement **Europe/Paris**.

## Dates et fiabilité

**OM et tri : dates prévisionnelles.** La source fournit des jours de semaine et non un agenda complet de toutes les exceptions. Le 1er janvier, le 1er mai et le 25 décembre sont exclus de la récurrence conformément à la règle officielle. Les autres jours fériés restent collectés selon la tournée. **Les rattrapages ne sont pas déduits automatiquement** : ajouter les dates confirmées par le calendrier communal. Les grèves, travaux et modifications ponctuelles peuvent nécessiter une correction manuelle.

La recherche propose des tronçons dans un rayon de 150 mètres et les classe selon la distance à la géométrie de la rue. Elle ne détermine pas le côté d’une rue à partir du numéro. Un libellé ambigu est refusé ; passer la sélection, puis saisir la règle confirmée dans les options. En l’absence de tronçon publié dans ce rayon, passer la sélection et utiliser les autres flux ou des dates confirmées. L’appartenance aux 37 communes est vérifiée par le code INSEE renvoyé par IGN.

**Végétaux : calendrier annuel borné.** En 2026, les passages payants commencent le 5 janvier, s’arrêtent du 10 au 21 août inclus puis à partir du 21 décembre ; le passage du vendredi 1er mai est reporté au 2 mai. Les six collectes saisonnières sont ajoutées. Le statut `expired` signale la fin de validité du calendrier. Les exceptions payantes de 2027 nécessiteront une mise à jour de l’intégration, ou la saisie des dates confirmées reçues par l’abonné. Les dates saisonnières d’une nouvelle année peuvent suivre la source dès leur publication.

En cas d’erreur réseau ou de disparition d’un tronçon, le flux concerné devient indisponible et son capteur de statut affiche une erreur ; les autres flux continuent de fonctionner. L’intégration ne présente pas d’ancien calendrier comme fraîchement vérifié.

## Entités et rappels

Chaque type possède un calendrier avec événements sur la journée, un capteur de date et un capteur de statut. Les identifiants exacts sont attribués par Home Assistant selon le nom de l’adresse.

Attributs utiles du capteur de date : `days_until`, `collection_today`, `collection_tomorrow`, `mode`, `rule`, `source_url`, `valid_until`, `error`. La prochaine date inclut aujourd’hui jusqu’à minuit. Une valeur inconnue signifie qu’aucune date n’est disponible, pas qu’une collecte a été annulée.

Pour un rappel la veille à 19 h, créer une automatisation avec un **déclencheur calendrier**, au début de l’événement, avec décalage **-05:00:00**, puis choisir une action de notification. Les événements commencent à minuit, donc cinq heures avant correspond à 19 h la veille. Aucun message n’est envoyé automatiquement par cette intégration.

Les capteurs de statut apparaissent dans les diagnostics de l’appareil. `recurring` indique une récurrence prévisionnelle ; `manual` des dates renseignées ou fournies par le calendrier végétaux ; `appointment` un rendez-vous à renseigner ; `drop_off` un dispositif d’apport ; `not_configured` un calendrier absent ; `error` une source en erreur ; `expired` un calendrier annuel expiré.

## Données et vie privée

La recherche d’adresse est envoyée au service de géocodage IGN. Les coordonnées sont envoyées aux API publiques Toulouse Métropole. L’adresse et les choix sont conservés dans l’entrée Home Assistant. Aucune clé d’API ni compte MonToulouse n’est nécessaire ; aucune télémétrie tierce n’est ajoutée. Supprimer l’intégration retire sa configuration Home Assistant ; l’historique déjà enregistré relève des réglages Recorder de votre installation.

Sources et détails des endpoints : [docs/SOURCES.md](docs/SOURCES.md).

## Développement

Python 3.14.2 minimum, puis depuis ce dossier :

```sh
python3.14 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q
.venv/bin/ruff check .
.venv/bin/ruff format --check .
```

Les tests couvrent les calendriers, les clients HTTP, les flux de configuration et les entités avec les classes réelles Home Assistant. Ils n’appellent pas les services publics. Les vérifications réseau manuelles utilisent uniquement des adresses publiques.

## Contributions et licence

Les [issues GitHub](https://github.com/estebanneuu/ha-toulouse-metropole-dechets/issues) accueillent les problèmes et propositions. Éviter de publier une adresse personnelle complète ; une commune et un libellé de tournée suffisent généralement pour commencer.

Code et icône originale : [licence MIT](LICENSE). Données publiques : attribution Toulouse Métropole, voir [les sources et leurs limites](docs/SOURCES.md). L’icône de l’intégration n’est pas le logo officiel de la collectivité.
