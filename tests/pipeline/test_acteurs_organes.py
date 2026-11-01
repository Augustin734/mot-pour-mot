"""Tests de la collecte « acteurs et organes » sur une petite archive fictive.

La structure reproduit celle de l'archive AMO30 réelle (vérifiée le 1er novembre 2026) ;
les personnes sont inventées.
"""

import json
import logging
import zipfile
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import Connection, select

from db.modeles import Appartenance, Depute, Groupe, Legislature
from pipeline.acteurs_organes import (
    FICHIER_ORDRE,
    charger,
    circonscription,
    lire_archive,
    lire_ordre_hemicycle,
)


def organe(uid: str, code_type: str, legislature: str, debut: str, fin: str | None = None, **autres) -> dict:
    return {
        "organe": {
            "uid": uid,
            "codeType": code_type,
            "legislature": legislature,
            "viMoDe": {"dateDebut": debut, "dateAgrement": None, "dateFin": fin},
            **autres,
        }
    }


def groupe(uid: str, sigle: str, couleur: str, legislature: str = "17") -> dict:
    return organe(
        uid, "GP", legislature, "2024-07-18", libelle=f"Groupe {sigle}", libelleAbrev=sigle, couleurAssociee=couleur
    )


def mandat_depute(uid: str, legislature: str, debut: str, departement: str, numero: str) -> dict:
    return {
        "uid": uid,
        "legislature": legislature,
        "typeOrgane": "ASSEMBLEE",
        "dateDebut": debut,
        "dateFin": None,
        "election": {"lieu": {"departement": departement, "numCirco": numero}},
    }


def mandat_groupe(uid: str, groupe_id: str, qualite: str, debut: str, fin: str | None = None) -> dict:
    return {
        "uid": uid,
        "legislature": "17",
        "typeOrgane": "GP",
        "dateDebut": debut,
        "dateFin": fin,
        "infosQualite": {"codeQualite": qualite},
        "organes": {"organeRef": groupe_id},
    }


def acteur(uid: str, prenom: str, nom: str, mandats: list[dict]) -> dict:
    return {
        "acteur": {
            "uid": {"@xsi:type": "IdActeur_type", "#text": uid},
            "etatCivil": {"ident": {"prenom": prenom, "nom": nom}},
            # Un seul mandat : l'AN donne un objet au lieu d'une liste.
            "mandats": {"mandat": mandats[0] if len(mandats) == 1 else mandats},
        }
    }


@pytest.fixture
def archive(tmp_path: Path) -> Path:
    fichiers = {
        "organe/PO1": organe("PO1", "ASSEMBLEE", "17", "2024-07-01"),
        "organe/PO2": organe("PO2", "ASSEMBLEE", "16", "2022-06-22", "2024-06-09"),
        "organe/PO10": groupe("PO10", "VERT", "#00AA00"),
        "organe/PO11": groupe("PO11", "BLEU", "#0000AA"),
        "organe/PO12": groupe("PO12", "NI", "#888888"),
        "organe/PO20": groupe("PO20", "ANCIEN", "#000000", legislature="16"),
        "organe/PO30": organe("PO30", "COMPER", "17", "2024-07-20"),
        # Députée : non-inscrite au début, puis membre et présidente de son groupe.
        "acteur/PA1": acteur(
            "PA1",
            "Camille",
            "Fictive",
            [
                mandat_depute("PM1", "17", "2024-07-07", "Paris", "1"),
                mandat_groupe("PM2", "PO12", "Député non-inscrit", "2024-07-08", "2024-07-18"),
                mandat_groupe("PM3", "PO10", "Membre", "2024-07-19"),
                mandat_groupe("PM4", "PO10", "Président", "2024-07-19"),
            ],
        ),
        # Un seul mandat (objet et non liste), de député, sans groupe.
        "acteur/PA2": acteur("PA2", "Dominique", "Exemple", [mandat_depute("PM5", "17", "2024-07-07", "Gironde", "3")]),
        # Ministre non député : pas dans la table depute.
        "acteur/PA3": acteur(
            "PA3", "Alex", "Ministre", [{"uid": "PM6", "legislature": None, "typeOrgane": "GOUVERNEMENT"}]
        ),
        # Député de la 16e seulement.
        "acteur/PA4": acteur("PA4", "Sacha", "Ancien", [mandat_depute("PM7", "16", "2022-06-19", "Nord", "2")]),
    }
    chemin = tmp_path / "AMO30.json.zip"
    with zipfile.ZipFile(chemin, "w") as zip_:
        for nom, contenu in fichiers.items():
            zip_.writestr(f"json/{nom}.json", json.dumps(contenu))
        zip_.writestr("json/deport/X.json", json.dumps({"deport": {}}))
    return chemin


ORDRE = {"PO10": 1, "PO11": 2, "PO12": 3}


def test_lecture(archive: Path) -> None:
    ref = lire_archive(archive, 17, ORDRE)

    assert sorted(l["numero"] for l in ref.legislatures) == [16, 17]
    assert {g["sigle"]: (g["couleur"], g["ordre_hemicycle"]) for g in ref.groupes} == {
        "VERT": ("#00AA00", 1),
        "BLEU": ("#0000AA", 2),
        "NI": ("#888888", 3),
    }
    assert {d["id"]: d["circonscription"] for d in ref.deputes} == {"PA1": "Paris (1re)", "PA2": "Gironde (3e)"}
    assert {(a["id"], a["groupe_id"], a["qualite"], a["fin"]) for a in ref.appartenances} == {
        ("PM2", "PO12", "non_inscrit", date(2024, 7, 18)),
        ("PM3", "PO10", "membre", None),
        ("PM4", "PO10", "president", None),
    }


def test_groupe_absent_du_fichier_d_ordre_signale(archive: Path, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING):
        ref = lire_archive(archive, 17, {"PO10": 1})
    assert {g["sigle"]: g["ordre_hemicycle"] for g in ref.groupes}["BLEU"] is None
    assert "PO11 (BLEU) absent" in caplog.text


def test_qualite_inconnue_refusee(tmp_path: Path) -> None:
    chemin = tmp_path / "AMO30.json.zip"
    with zipfile.ZipFile(chemin, "w") as zip_:
        zip_.writestr("json/organe/PO10.json", json.dumps(groupe("PO10", "VERT", "#00AA00")))
        zip_.writestr(
            "json/acteur/PA1.json",
            json.dumps(
                acteur(
                    "PA1",
                    "Camille",
                    "Fictive",
                    [
                        mandat_depute("PM1", "17", "2024-07-07", "Paris", "1"),
                        mandat_groupe("PM2", "PO10", "Vice-président", "2024-07-19"),
                    ],
                )
            ),
        )
    with pytest.raises(ValueError, match="Vice-président"):
        lire_archive(chemin, 17, {})


def test_chargement_idempotent_et_corrections(connexion: Connection, archive: Path) -> None:
    ref = lire_archive(archive, 17, ORDRE)

    assert charger(connexion, ref) == {"legislatures": 2, "groupes": 3, "deputes": 2, "appartenances": 3}
    assert charger(connexion, ref) == {"legislatures": 0, "groupes": 0, "deputes": 0, "appartenances": 0}

    # Une correction de l'open data met la ligne à jour, sans doublon.
    ref.deputes[0]["nom"] = "Fictive-Corrigée"
    assert charger(connexion, ref)["deputes"] == 1
    assert connexion.scalar(select(Depute.nom).where(Depute.id == "PA1")) == "Fictive-Corrigée"
    assert connexion.scalar(select(Legislature.fin).where(Legislature.numero == 16)) == date(2024, 6, 9)
    groupe_actuel = connexion.scalar(
        select(Groupe.sigle)
        .join(Appartenance, Appartenance.groupe_id == Groupe.id)
        .where(Appartenance.depute_id == "PA1", Appartenance.debut <= date(2026, 1, 1))
        .where((Appartenance.fin.is_(None)) | (Appartenance.fin >= date(2026, 1, 1)))
        .distinct()
    )
    assert groupe_actuel == "VERT"


def test_legislature_existante_mise_a_jour(connexion: Connection, archive: Path) -> None:
    """Une législature créée par le référentiel provisoire prend les dates de l'open data."""
    connexion.execute(Legislature.__table__.insert().values(numero=17, debut=date(2024, 7, 18)))
    charger(connexion, lire_archive(archive, 17, ORDRE))
    assert connexion.scalar(select(Legislature.debut).where(Legislature.numero == 17)) == date(2024, 7, 1)


def test_circonscription() -> None:
    assert circonscription({"departement": "Bas-Rhin", "numCirco": "6"}) == "Bas-Rhin (6e)"
    assert circonscription({"departement": "Paris", "numCirco": "1"}) == "Paris (1re)"
    assert circonscription({"departement": None}) is None


def test_fichier_d_ordre_reel() -> None:
    """Le fichier versionné se lit, couvre les 14 groupes de la 17e et va de 1 à 12."""
    ordre = lire_ordre_hemicycle(FICHIER_ORDRE, 17)
    assert len(ordre) == 14
    assert sorted(set(ordre.values())) == list(range(1, 13))
    assert lire_ordre_hemicycle(FICHIER_ORDRE, 16) == {}
