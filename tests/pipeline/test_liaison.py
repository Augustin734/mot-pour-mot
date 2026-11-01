"""Tests de la liaison : groupe à la date, dossier des points et des interventions.

Données fictives (charte de neutralité : aucun propos réel inventé).
"""

import pytest
from sqlalchemy import Connection, insert, select, update

from db.modeles import (
    Appartenance,
    Depute,
    Dossier,
    Groupe,
    Intervention,
    Legislature,
    PointOdj,
    Seance,
    Texte,
)
from pipeline.liaison import index_des_titres, lier, normaliser_titre


@pytest.fixture
def base(connexion: Connection) -> Connection:
    c = connexion
    c.execute(insert(Legislature).values(numero=17, debut="2024-07-01"))
    c.execute(
        insert(Groupe),
        [
            {"id": "PO1", "legislature": 17, "sigle": "VERT", "nom": "Groupe vert"},
            {"id": "PO2", "legislature": 17, "sigle": "BLEU", "nom": "Groupe bleu"},
        ],
    )
    c.execute(
        insert(Depute),
        [
            {"id": "PA1", "nom": "Fictive", "prenom": "Camille"},  # change de groupe le 1er mars 2025
            {"id": "PA2", "nom": "Exemple", "prenom": "Alex"},  # député devenu ministre
            {"id": "PA3", "nom": "Modèle", "prenom": "Sacha"},  # vice-président de séance
        ],
    )
    c.execute(
        insert(Appartenance),
        [
            {"id": "PM1", "depute_id": "PA1", "groupe_id": "PO1", "qualite": "membre", "debut": "2024-07-19", "fin": "2025-02-28"},
            {"id": "PM2", "depute_id": "PA1", "groupe_id": "PO2", "qualite": "membre", "debut": "2025-03-01", "fin": None},
            {"id": "PM3", "depute_id": "PA2", "groupe_id": "PO2", "qualite": "membre", "debut": "2024-07-19", "fin": None},
            {"id": "PM4", "depute_id": "PA3", "groupe_id": "PO1", "qualite": "membre", "debut": "2024-07-19", "fin": None},
        ],
    )
    c.execute(
        insert(Dossier),
        [
            {"id": "DLR1", "legislature": 17, "titre_officiel": "Proposition de loi visant à protéger les haies", "type": "proposition"},
            {"id": "DLR2", "legislature": 17, "titre_officiel": "Proposition de loi relative aux ponts", "type": "proposition"},
            {"id": "DLR3", "legislature": 17, "titre_officiel": "Projet de loi de finances pour 2026", "type": "projet"},
            {"id": "DLR4", "legislature": 17, "titre_officiel": "Instaurer une motion de censure constructive", "type": "proposition"},
        ],
    )
    c.execute(
        insert(Texte),
        [
            {"legislature": 17, "numero": "100", "dossier_id": "DLR1", "type": "depose"},
            {"legislature": 17, "numero": "200", "dossier_id": "DLR2", "type": "depose"},
        ],
    )
    c.execute(
        insert(Seance),
        [
            {"id": "S1", "legislature": 17, "debut": "2025-01-15T15:00:00+01:00"},
            {"id": "S2", "legislature": 17, "debut": "2025-10-20T21:30:00+02:00"},
        ],
    )
    c.execute(
        insert(PointOdj),
        [
            {"id": "S1-P1", "seance_id": "S1", "numero": 1, "titre": "Protection des haies"},
            {"id": "S2-P1", "seance_id": "S2", "numero": 1, "titre": "Projet de loi de finances pour 2026"},
            {"id": "S2-P2", "seance_id": "S2", "numero": 2, "titre": "Motion de censure"},
        ],
    )

    def intervention(seance, ordre, point, acteur, qualite, numero=None):
        return {
            "seance_id": seance,
            "ordre": ordre,
            "point_id": point,
            "acteur_id": acteur,
            "orateur_libelle": acteur,
            "qualite": qualite,
            "numero_texte": numero,
            "texte": "Propos fictif.",
        }

    c.execute(
        insert(Intervention),
        [
            intervention("S1", 1, "S1-P1", "PA3", "president", "100"),
            intervention("S1", 2, "S1-P1", "PA1", "depute", "100"),
            intervention("S1", 3, "S1-P1", "PA1", "depute", "100"),
            # Discussion commune : un paragraphe porte le numéro d'un autre texte.
            intervention("S1", 4, "S1-P1", "PA1", "rapporteur", "200"),
            intervention("S1", 5, "S1-P1", "PA2", "ministre", "100"),
            intervention("S2", 1, "S2-P1", "PA1", "depute"),
            # Numéro absent de texte (résolution) : reste sans dossier.
            intervention("S2", 2, "S2-P2", "PA1", "depute", "999"),
            # Orateur qui n'est pas député.
            intervention("S2", 3, "S2-P2", "PA9", "ministre"),
        ],
    )
    return c


def lignes(connexion: Connection) -> dict:
    resultat = connexion.execute(
        select(Intervention.seance_id, Intervention.ordre, Intervention.depute_id, Intervention.groupe_id, Intervention.dossier_id)
    ).all()
    return {(s, o): (d, g, dos) for s, o, d, g, dos in resultat}


def test_liaison(base: Connection) -> None:
    lier(base, 17)
    resultat = lignes(base)

    # Groupe à la date de la séance : VERT en janvier, BLEU en octobre.
    assert resultat[("S1", 2)] == ("PA1", "PO1", "DLR1")
    assert resultat[("S2", 1)] == ("PA1", "PO2", "DLR3")
    # Président de séance et ministre : identifiés, mais leur parole n'est pas celle d'un groupe.
    assert resultat[("S1", 1)][:2] == ("PA3", None)
    assert resultat[("S1", 5)][:2] == ("PA2", None)
    assert resultat[("S2", 3)] == (None, None, None)
    # Le numéro propre de l'intervention l'emporte sur le dossier du point.
    assert resultat[("S1", 4)] == ("PA1", "PO1", "DLR2")
    assert resultat[("S2", 2)][2] is None

    points = dict(base.execute(select(PointOdj.id, PointOdj.dossier_id)).all())
    assert points == {"S1-P1": "DLR1", "S2-P1": "DLR3", "S2-P2": None}


def test_bilan_et_idempotence(base: Connection) -> None:
    premier = lier(base, 17)
    assert (premier.interventions, premier.avec_dossier) == (8, 6)
    assert (premier.parlementaires, premier.avec_groupe) == (5, 5)
    assert premier.numeros_inconnus == [("999", 1)]

    assert lier(base, 17).ecritures == {"orateurs": 0, "points": 0, "dossiers": 0}


def test_correction_propagee(base: Connection) -> None:
    lier(base, 17)
    # L'open data corrige la date du changement de groupe : la séance de janvier passe en BLEU.
    base.execute(update(Appartenance).where(Appartenance.id == "PM1").values(fin="2025-01-10"))
    base.execute(update(Appartenance).where(Appartenance.id == "PM2").values(debut="2025-01-11"))

    assert lier(base, 17).ecritures["orateurs"] == 3
    assert lignes(base)[("S1", 2)][1] == "PO2"


@pytest.mark.parametrize(
    ("titre", "attendu"),
    [
        ("Projet de loi de finances pour 2026", "finances pour 2026"),
        ("Proposition de loi visant à sortir la France du piège du narcotrafic", "sortir la france du piege du narcotrafic"),
        ("Sortir la France du piège du narcotrafic (suite)", "sortir la france du piege du narcotrafic"),
        ("Projet de loi de financement de la sécurité sociale pour 2025\nL’ordre du jour…", "financement de la securite sociale pour 2025"),
        ("Proposition de loi organique relative à l’élection", "election"),
    ],
)
def test_normaliser_titre(titre: str, attendu: str) -> None:
    assert normaliser_titre(titre) == attendu


def test_titres_ambigus_ecartes() -> None:
    index = index_des_titres([("D1", "Proposition de loi sur les haies"), ("D2", "Projet de loi sur les haies"), ("D3", "Ponts")])
    assert index == {"ponts": "D3"}
