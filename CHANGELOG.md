# Historique

## 0.1.1 — 2026-11-20

- Correction d’un échec à la confirmation de l’adresse : un tronçon OpenData sans nom de voie, sans règle ou sans géométrie utilisable ne bloque plus les autres tournées valides de la réponse.
- Les réponses entièrement inexploitables restent signalées, distinctement d’une absence de couverture.
- Les erreurs de données et les erreurs réseau affichent désormais des messages différents.
- Huit tests de régression supplémentaires couvrent le client et le parcours de configuration.

Après mise à jour dans HACS, redémarrer Home Assistant puis relancer la configuration.

## 0.1.0 — 2026-11-20

- Première version publique pour Home Assistant 2026.11+.
- Configuration par adresse dans les 37 communes de Toulouse Métropole.
- Calendriers et capteurs pour sept types de déchets.
- Tournées OM et tri depuis l’Open Data, avec parité des semaines ISO.
- Calendrier des végétaux gratuit et payant ; exceptions payantes validées pour 2026.
- Dates manuelles pour les rendez-vous et les cas particuliers, ajouts et exclusions.
- Statuts explicites pour l’apport volontaire, les erreurs et les calendriers expirés.
- Tests des clients HTTP, des calculs de dates et du chargement des plateformes Home Assistant.

Les rattrapages OM/tri doivent être renseignés manuellement. Le calendrier payant des végétaux de 2027 nécessitera une nouvelle validation des exceptions annuelles.
