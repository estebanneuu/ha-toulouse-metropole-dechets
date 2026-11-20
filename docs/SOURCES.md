# Sources et limites des données

Vérification des services publics le **20 novembre 2026**. Aucune clé API ni aucun compte MonToulouse n'est utilisé. Les jeux ouverts sont publiés sous Licence Ouverte 2.0 ; attribution : Toulouse Métropole. L'API cartographique des végétaux est un service public consultable sans connexion, mais son contrat technique n'est pas documenté comme celui de l'Open Data.

## Ordures ménagères et emballages/papiers

Portail officiel : [ordures ménagères](https://data.toulouse-metropole.fr/explore/dataset/dechets-collecte-des-ordures-menageres/) et [collecte sélective](https://data.toulouse-metropole.fr/explore/dataset/dechets-collecte-selective/).

Racine des requêtes JSON :

```text
https://data.toulouse-metropole.fr/api/explore/v2.1/catalog/datasets/{dataset_id}/records
```

Identifiants : `dechets-collecte-des-ordures-menageres` et `dechets-collecte-selective`. Les champs utiles sont `geo_shape`, `geo_point_2d`, `libelle_voie`, `flux` et `infobulle_pdi`. Les enregistrements décrivent des tronçons de voie, pas un calendrier daté individuel. La localisation et le choix du tronçon doivent donc être vérifiés lors de la configuration ; un tronçon proche ne prouve pas à lui seul qu'il dessert le domicile.

Les règles hebdomadaires ne renseignent pas tous les reports exceptionnels, jours fériés ou interruptions de service. La page [déchets dans ma commune](https://metropole.toulouse.fr/mon-environnement/dechets-et-proprete/les-dechets-dans-ma-commune) renvoie aux calendriers municipaux de référence. Aucun report n'est déduit de la seule proximité d'un jour férié.

La [page officielle Toulouse](https://metropole.toulouse.fr/communes/toulouse) précise pour toutes les communes l'absence de collecte OM et tri les 1er janvier, 1er mai et 25 décembre. Ces dates sont exclues des récurrences ; les rattrapages sont à renseigner séparément. L'appartenance aux 37 communes est vérifiée par une liste de codes INSEE issue de l'[API gouvernementale, EPCI 243100518](https://geo.api.gouv.fr/epcis/243100518/communes?fields=code,nom), vérifiée le 20 novembre 2026. L'adresse et son code INSEE proviennent du [géocodeur IGN](https://data.geopf.fr/geocodage/search).

## Déchets végétaux

La [page officielle des déchets végétaux](https://metropole.toulouse.fr/mon-environnement/dechets-et-proprete/les-dechets-vegetaux) propose deux forfaits sur inscription : saisonnier gratuit et annuel payant. Elle renvoie aux [secteurs de Toulouse](https://carto.toulouse.fr/PDI/?context=Gqmf) et aux [autres communes](https://carto.toulouse-metropole.fr/TOULOUSE_METROPOLE/?context=muNz).

La couche publique utilisée par la carte Toulouse renvoie également les secteurs des autres communes : 46 secteurs observés au total. Le code effectue une intersection spatiale avec le point choisi et refuse des secteurs contradictoires à une frontière.

```text
POST https://carto.toulouse.fr/PDI/services/aas/v1/searches/execute
Content-Type: application/x-www-form-urlencoded

searchIds=7e7a3ad9-1620-11f1-92ed-5d0ff281562c
srid=4326
useExtent=true
limit=100
offset=0
centroid=true
simplifyGeometry=false
filters={}
spatialFilter={"type":"Point","coordinates":[longitude,latitude],"crs":{"type":"name","properties":{"name":"EPSG:4326"}}}
```

La réponse GeoJSON contient `features[].properties.oid`, `type_collecte` et `infobulle`. L'infobulle contient un jour et une parité de semaine pour le forfait payant et six dates explicites au format `JJ/MM/AAAA` pour le forfait saisonnier. Ces dernières sont conservées telles que publiées, y compris lorsqu'une date change de jour de semaine.

Si l'identifiant de recherche devient invalide, `green.py` cherche à nouveau la ressource nommée « Collecte déchets verts » dans le descripteur public :

```text
GET https://carto.toulouse.fr/PDI/services/aas/v1/applications/getApplicationDescriptor
    ?id=724214d6-b9f5-11e9-943b-f9610daa8d23&translationKey=fr
```

Le [calendrier officiel du forfait payant 2026](https://metropole.toulouse.fr/sites/toulouse-fr/files/2026-02/telecharger_le_calendrier_des_collectes_pour_les_abonnes_forfait_payant_05.02.2026_1.pdf), vérifié visuellement, précise le démarrage au 5 janvier, l'interruption du 10 au 21 août et celle à partir du 21 décembre jusqu'au 1er janvier 2027 inclus. Le passage du 1er mai est reporté au 2 mai. Les abonnés payants bénéficient également des six passages saisonniers.

Ces exceptions sont encodées **pour 2026 seulement**. Un calendrier payant 2027 demande une mise à jour après vérification de la nouvelle publication. Les dates saisonnières peuvent suivre les années explicitement publiées par la carte ; aucune date n'est reportée automatiquement sur l'année suivante. Une absence de date future après expiration des données ne signifie pas une suppression du service.

Validation : les 46 réponses 2026 donnent chacune six dates saisonnières et 30 dates au total pour les abonnés payants. Les tests couvrent notamment le report du 1er mai, l'été, le changement d'année, les frontières de secteurs et les erreurs réseau. Des requêtes réelles ont vérifié un point public du centre de Toulouse, un point de Blagnac, une position hors métropole et la redécouverte d'une couche.

## Verre, déchets alimentaires et textiles

Les jeux officiels [points d'apport volontaire](https://data.toulouse-metropole.fr/explore/dataset/points-dapport-volontaire-dechets-et-moyens-techniques/) et [conteneurs d'apport volontaire](https://data.toulouse-metropole.fr/explore/dataset/dmt_cav/) exposent leurs emplacements et leurs caractéristiques via la même API Open Data.

Champs vérifiés : `id_cav`, `geo_point_2d`, `type_flux`, `etat_fonctionnement`, `commune`, `voie` et `type_flux_etat_fonctionnement`. `dmt_cav` contient également `frequence_collecte` pour certains conteneurs, sans dates de passage. Une fréquence d'entretien des bornes n'est pas un jour où l'habitant doit sortir une poubelle. Aucun calendrier de collecte à domicile n'est donc fabriqué pour ces flux.

## Encombrants

La [démarche officielle de collecte des encombrants](https://metropole.toulouse.fr/demarches/collecte-encombrants) prévoit une prise de rendez-vous pour Toulouse et les 36 autres communes. Aucun calendrier public individuel n'a été identifié. Une date renseignée dans Home Assistant doit correspondre à un rendez-vous déjà confirmé ; cette intégration ne réserve aucun passage.
