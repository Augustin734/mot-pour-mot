"""Tests du parseur Syceron sur le format de l'export réel de la 17e législature."""

from datetime import datetime
from pathlib import Path

import pytest

from pipeline.syceron import FUSEAU_AN, CompteRenduInvalide, SeanceLue, lire_fichier, lire_xml, nettoyer_numero_texte

FICHIER = Path(__file__).parent / "donnees" / "compte_rendu_17_mini.xml"


@pytest.fixture(scope="module")
def seance() -> SeanceLue:
    (seance,) = lire_fichier(FICHIER)
    return seance


@pytest.fixture(scope="module")
def interventions(seance: SeanceLue) -> dict:
    return {i.ordre: i for i in seance.interventions}


def test_identifiant_officiel_et_date(seance: SeanceLue) -> None:
    assert seance.id == "RUANR5L17S2025IDS99999"
    assert seance.legislature == 17
    assert seance.debut == datetime(2025, 1, 15, 15, 0, tzinfo=FUSEAU_AN)


def test_tous_les_blocs_sont_lus(interventions: dict) -> None:
    # Ouverture, discussion générale (dans un interExtraction), articles, changement de
    # présidence et questions : rien n'est perdu.
    assert sorted(interventions) == [2, 7, 10, 11, 12, 14, 16]
    assert interventions[14].texte == "La séance est reprise."


@pytest.mark.parametrize(
    ("valeur", "attendu"),
    [
        (" 912", "912"),
        (" 912 rectifié", "912"),
        (" (n[[o]]\xa03851)", "3851"),
        (" (n[[os]\xa01281 et 1364)", "1281"),  # marqueur mal fermé
        (" (n[[os] ] 907,\xa01043 rectifié, 908)", "907"),
        (" ", None),
    ],
)
def test_bibard_de_l_export_reel(valeur: str, attendu: str | None) -> None:
    assert nettoyer_numero_texte(valeur, nombre_seul=True) == attendu


def test_nombre_seul_refuse_hors_bibard() -> None:
    """Dans l'attribut valeur d'un point, « 912 » est un article ou un amendement."""
    assert nettoyer_numero_texte(" 912") is None


def test_numero_propage_dans_le_point(seance: SeanceLue, interventions: dict) -> None:
    # La discussion générale n'a pas de bibard : elle reçoit le numéro le plus fréquent du point.
    assert interventions[7].numero_texte == "912"
    assert interventions[14].numero_texte == "912"  # changement de présidence dans le point 1
    assert seance.points[0].numero_texte == "912"


def test_numero_propre_garde_en_discussion_commune(interventions: dict) -> None:
    assert interventions[12].numero_texte == "1281"


def test_point_sans_texte(interventions: dict) -> None:
    assert interventions[16].numero_texte is None
    assert interventions[16].type_debat == "Questions au Gouvernement"


def test_qualites(interventions: dict) -> None:
    assert interventions[2].qualite == "president"
    assert interventions[7].qualite == "rapporteur"  # qualité portée par le bloc
    assert interventions[12].qualite == "ministre"
    assert interventions[10].qualite == "depute"
    assert (interventions[10].article, interventions[10].amendement) == ("1er", "6")


def test_rangs_en_double_refuses() -> None:
    """Version provisoire mal numérotée : refusée plutôt que chargée de travers."""
    contenu = FICHIER.read_bytes().replace(b'ordre_absolu_seance="11"', b'ordre_absolu_seance="10"')
    with pytest.raises(CompteRenduInvalide, match="1 rangs"):
        list(lire_xml(contenu))
