"""Shared integration constants."""

DOMAIN = "toulouse_metropole_dechets"
NAME = "Toulouse Métropole Déchets"
# Official EPCI 243100518 membership, geo.api.gouv.fr, checked 2026-11-20.
MUNICIPALITY_CODES = frozenset(
    {
        "31003",
        "31022",
        "31032",
        "31044",
        "31053",
        "31056",
        "31069",
        "31088",
        "31091",
        "31116",
        "31149",
        "31150",
        "31157",
        "31163",
        "31182",
        "31184",
        "31186",
        "31205",
        "31230",
        "31282",
        "31293",
        "31351",
        "31352",
        "31355",
        "31389",
        "31417",
        "31418",
        "31445",
        "31467",
        "31488",
        "31490",
        "31506",
        "31541",
        "31555",
        "31557",
        "31561",
        "31588",
    }
)
STREAMS = {
    "om": "Ordures ménagères",
    "tri": "Emballages et papiers",
    "green": "Déchets végétaux",
    "bulky": "Encombrants",
    "glass": "Verre",
    "food": "Déchets alimentaires",
    "textile": "Textiles",
}
ICONS = {
    "om": "mdi:trash-can",
    "tri": "mdi:recycle",
    "green": "mdi:leaf",
    "bulky": "mdi:sofa",
    "glass": "mdi:bottle-wine",
    "food": "mdi:food-apple",
    "textile": "mdi:tshirt-crew",
}
DATASETS = {
    "om": "dechets-collecte-des-ordures-menageres",
    "tri": "dechets-collecte-selective",
}
OFFICIAL_URL = "https://metropole.toulouse.fr/mon-environnement/dechets-et-proprete/les-dechets-dans-ma-commune"
GREEN_URL = "https://metropole.toulouse.fr/mon-environnement/dechets-et-proprete/les-dechets-vegetaux"
MODES = {
    "recurring": "Tournée hebdomadaire publiée (dates prévisionnelles)",
    "manual": "Dates confirmées saisies",
    "drop_off": "Apport volontaire / compostage, sans jour de passage à domicile",
    "appointment": "Sur rendez-vous, aucune date enregistrée",
    "unavailable": "Calendrier non renseigné ou non disponible",
}
