"""Tests du parseur Syceron, sur un compte rendu fictif qui reprend la structure réelle."""

from datetime import datetime
from pathlib import Path

import pytest

from pipeline.syceron import (
    FUSEAU_AN,
    SeanceLue,
    lire_fichier,
    nettoyer_numero_texte,
    qualite_orateur,
)

FICHIER = Path(__file__).parent / "donnees" / "comptes_rendus_mini.xml"


@pytest.fixture(scope="module")
def seances() -> list[SeanceLue]:
    return list(lire_fichier(FICHIER))


@pytest.fixture(scope="module")
def interventions(seances: list[SeanceLue]) -> dict:
    """Interventions de la première séance, par ordre dans la séance."""
    return {i.ordre: i for i in seances[0].interventions}


@pytest.mark.parametrize(
    ("valeur", "attendu"),
    [
        ("(n[[o]]\xa03851)", "3851"),
        (" (n[[os]]\xa0611, 3749)", "611"),  # le premier numéro est le texte discuté
        ("", None),
        (None, None),
        (". ", None),
        ("695511 1699. ", None),  # nombres sans « n° » : pas un numéro de texte
    ],
)
def test_nettoyer_numero_texte(valeur: str | None, attendu: str | None) -> None:
    assert nettoyer_numero_texte(valeur) == attendu


@pytest.mark.parametrize(
    ("nom", "qualite", "role", "attendu"),
    [
        ("M. le président", "", None, "president"),
        ("Mme Alice Exemple", "ministre de l’agriculture", None, "ministre"),
        ("M. Bruno Témoin", "secrétaire d’État chargé du budget", None, "ministre"),
        ("Mme Claire Fictive", "rapporteure de la commission", None, "rapporteur"),
        ("Mme Claire Fictive", "présidente de la commission des lois", None, "depute"),
        ("M. Paul Exemple", "", "president", "president"),
    ],
)
def test_qualite_orateur(nom: str, qualite: str, role: str | None, attendu: str) -> None:
    assert qualite_orateur(nom, qualite, role) == attendu


def test_seance_identifiant_et_date(seances: list[SeanceLue]) -> None:
    assert [s.id for s in seances] == ["ECH-L14-201406301600", "ECH-L14-201306121500"]
    assert seances[0].debut == datetime(2014, 6, 30, 16, 0, tzinfo=FUSEAU_AN)
    assert seances[0].legislature == 14


def test_points_de_l_ordre_du_jour(seances: list[SeanceLue]) -> None:
    points = seances[0].points
    assert [(p.id, p.numero, p.numero_texte) for p in points] == [
        ("ECH-L14-201406301600-P1", 1, "2044"),
        ("ECH-L14-201406301600-P2", 2, None),
    ]
    assert points[0].titre == "Projet de loi relatif aux jardins partagés"


def test_didascalie_sans_orateur_ignoree(interventions: dict) -> None:
    assert sorted(interventions) == [2, 8, 9, 11, 21]


def test_numero_texte_herite_du_point(interventions: dict) -> None:
    assert interventions[8].numero_texte == "2044"


def test_numero_texte_du_bibard_prioritaire(interventions: dict) -> None:
    assert interventions[11].numero_texte == "611"
    assert (interventions[11].article, interventions[11].amendement) == ("3", "12")


def test_qualite_du_bloc_reprise_pour_son_orateur(interventions: dict) -> None:
    assert interventions[8].qualite == "ministre"


def test_interruption_n_herite_pas_de_la_qualite_du_bloc(interventions: dict) -> None:
    interruption = interventions[9]
    assert interruption.qualite == "depute"
    assert interruption.code_grammaire == "INTERRUPTION_1_10"
    assert interruption.orateur_libelle == "M. Bruno Témoin"  # espace insécable normalisée


def test_texte_garde_didascalies_et_retours_a_la_ligne(interventions: dict) -> None:
    assert interventions[8].texte == (
        "Les jardins partagés sont (Applaudissements.) un bien commun.\nJe vous remercie."
    )
    assert interventions[8].nb_mots == 11


def test_type_debat(interventions: dict) -> None:
    assert interventions[2].type_debat is None  # ouverture de séance
    assert interventions[8].type_debat == "Discussion générale"  # « (suite) » retiré
    assert interventions[11].type_debat == "Discussion des articles"
    assert interventions[21].type_debat == "Questions au Gouvernement"


def test_metadonnees_en_minuscules(seances: list[SeanceLue]) -> None:
    seance = seances[1]
    assert seance.debut.year == 2013
    assert [i.qualite for i in seance.interventions] == ["president"]
