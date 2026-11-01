"""Tests de la collecte des dossiers législatifs sur une petite archive fictive.

La structure reproduit celle de l'archive Dossiers_Legislatifs réelle (vérifiée le
1er novembre 2026) ; les titres sont inventés.
"""

import json
import zipfile
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import Connection, insert, select

from db.modeles import Etape, Legislature, Texte
from pipeline.dossiers import charger, lire_archive, type_etape


def acte(uid: str, code: str, type_: str = "Etape_Type", date_acte: str | None = None, enfants=None, **autres) -> dict:
    return {
        "@xsi:type": type_,
        "uid": uid,
        "codeActe": code,
        "dateActe": date_acte,
        # Un seul sous-acte : l'AN donne un objet au lieu d'une liste.
        "actesLegislatifs": None
        if not enfants
        else {"acteLegislatif": enfants[0] if len(enfants) == 1 else enfants},
        **autres,
    }


def dossier(uid: str, legislature: str, titre: str, procedure: str, actes: list[dict], type_: str = "DossierLegislatif_Type") -> dict:
    return {
        "dossierParlementaire": {
            "@xsi:type": type_,
            "uid": uid,
            "legislature": legislature,
            "titreDossier": {"titre": titre},
            "procedureParlementaire": {"libelle": procedure},
            "actesLegislatifs": {"acteLegislatif": actes},
        }
    }


def document(uid: str, dossier_ref: str | None) -> dict:
    return {"document": {"uid": uid, "dossierRef": dossier_ref}}


@pytest.fixture
def archive(tmp_path: Path) -> Path:
    fichiers = {
        # Projet de loi promulgué, avec CMP ; l'étape AN1 n'a pas de date propre.
        "dossierParlementaire/DLR1": dossier(
            "DLR1",
            "17",
            "Projet de loi relatif aux jardins partagés",
            "Projet de loi ordinaire",
            [
                acte(
                    "L-AN1",
                    "AN1",
                    enfants=[
                        acte(
                            "A1-DEPOT",
                            "AN1-DEPOT",
                            "DepotInitiative_Type",
                            "2025-01-10T00:00:00.000+01:00",
                            texteAssocie="PRJLANR5L17B0100",
                        ),
                        acte(
                            "A1-COM",
                            "AN1-COM",
                            enfants=[acte("A1-COM-R", "AN1-COM-FOND-RAPPORT", "DepotRapport_Type", "2025-02-01T00:00:00.000+01:00")],
                        ),
                        acte("A1-DEB", "AN1-DEBATS", enfants=[acte("A1-DEB-S", "AN1-DEBATS-SEANCE", "DiscussionSeancePublique_Type", "2025-02-10T15:00:00.000+01:00")]),
                    ],
                ),
                acte("L-CMP", "CMP", enfants=[acte("CMP-C", "CMP-COM", date_acte="2025-03-01T00:00:00.000+01:00")]),
                acte("L-PROM", "PROM", enfants=[acte("PROM-1", "PROM-PUB", "Promulgation_Type", "2025-04-01T00:00:00.000+02:00")]),
            ],
        ),
        # Proposition « organique » (libellé ambigu) retirée.
        "dossierParlementaire/DLR2": dossier(
            "DLR2",
            "17",
            "Proposition de loi organique sur les horloges",
            "Projet ou proposition de loi organique",
            [
                acte(
                    "L2-AN1",
                    "AN1",
                    enfants=[
                        acte("A2-DEPOT", "AN1-DEPOT", "DepotInitiative_Type", "2025-05-01T00:00:00.000+02:00", texteAssocie="PIONANR5L17B0200"),
                        acte("A2-RET", "AN1-RTRINI", "RetraitInitiative_Type", "2025-06-01T00:00:00.000+02:00"),
                    ],
                ),
            ],
        ),
        # Dossier de la 16e encore discuté sous la 17e.
        "dossierParlementaire/DLR3": dossier("DLR3", "16", "Proposition de loi sur les ponts", "Proposition de loi ordinaire", []),
        # Dossier d'une législature absente de la base, et résolution : ignorés.
        "dossierParlementaire/DLR4": dossier("DLR4", "8", "Ancienne proposition", "Proposition de loi ordinaire", []),
        "dossierParlementaire/DLR5": dossier("DLR5", "17", "Résolution", "Résolution", [], type_="DossierResolutionAN"),
        "document/PRJLANR5L17B0100": document("PRJLANR5L17B0100", "DLR1"),
        # Le rapport et le texte de la commission partagent le numéro 150.
        "document/RAPPANR5L17B0150": document("RAPPANR5L17B0150", "DLR1"),
        "document/PRJLANR5L17BTC0150": document("PRJLANR5L17BTC0150", "DLR1"),
        # Texte adopté : autre numérotation, ignoré.
        "document/PRJLANR5L17BTA0100": document("PRJLANR5L17BTA0100", "DLR2"),
        "document/PIONANR5L17B0200": document("PIONANR5L17B0200", "DLR2"),
        "document/PIONANR5L17B0300": document("PIONANR5L17B0300", "DLR3"),
        "document/PNREANR5L17B0400": document("PNREANR5L17B0400", "DLR5"),
        "document/PIONANR5L17B0500": document("PIONANR5L17B0500", None),
        # Document du Sénat ou de la 16e : ignorés.
        "document/PIONSNR5S479B0100": document("PIONSNR5S479B0100", "DLR1"),
        "document/PIONANR5L16B0600": document("PIONANR5L16B0600", "DLR3"),
    }
    chemin = tmp_path / "Dossiers_Legislatifs.json.zip"
    with zipfile.ZipFile(chemin, "w") as zip_:
        for nom, contenu in fichiers.items():
            zip_.writestr(f"json/{nom}.json", json.dumps(contenu))
    return chemin


def test_dossiers(archive: Path) -> None:
    lus = lire_archive(archive, 17, {16, 17})
    dossiers = {d["id"]: d for d in lus.dossiers}

    assert set(dossiers) == {"DLR1", "DLR2", "DLR3"}
    assert (dossiers["DLR1"]["type"], dossiers["DLR1"]["statut"]) == ("projet", "adopte")
    assert (dossiers["DLR2"]["type"], dossiers["DLR2"]["statut"]) == ("proposition", "retire")
    assert dossiers["DLR3"]["statut"] == "en_cours"
    assert dossiers["DLR1"]["date_depot"] == date(2025, 1, 10)
    assert dossiers["DLR1"]["date_derniere_activite"].date() == date(2025, 4, 1)


def test_etapes(archive: Path) -> None:
    etapes = {e["id"]: e for e in lire_archive(archive, 17, {16, 17}).etapes}

    assert {i: (e["type"], e["chambre"]) for i, e in etapes.items()} == {
        "A1-DEPOT": ("depot", "an"),
        "A1-COM": ("commission", "an"),
        "A1-DEB": ("seance", "an"),
        "CMP-C": ("cmp", None),
        "PROM-1": ("promulgation", None),
        "A2-DEPOT": ("depot", "an"),
    }
    # Une étape sans date prend celle de son premier sous-acte.
    assert etapes["A1-COM"]["date"] == date(2025, 2, 1)


def test_textes(archive: Path) -> None:
    lus = lire_archive(archive, 17, {16, 17})

    assert {t["numero"]: (t["dossier_id"], t["type"]) for t in lus.textes} == {
        "100": ("DLR1", "depose"),
        "150": ("DLR1", "commission"),
        "200": ("DLR2", "depose"),
        "300": ("DLR3", "depose"),
    }
    assert lus.ignores == {"dossier non chargé (résolution, mission…)": 1, "sans dossier": 1}


def test_type_etape() -> None:
    assert type_etape("SN1-DEBATS") == ("seance", "senat")
    assert type_etape("ANLDEF-DEBATS") == ("lecture_definitive", "an")
    assert type_etape("ANNLEC-COM") == ("commission", "an")
    assert type_etape("CMP-DEBATS-SN") == ("seance", "senat")
    assert type_etape("AN1-PROCACC") is None
    assert type_etape("CC-CONCLUSION") is None


def test_chargement_idempotent(connexion: Connection, archive: Path) -> None:
    connexion.execute(insert(Legislature), [{"numero": 16, "debut": "2022-06-22"}, {"numero": 17, "debut": "2024-07-01"}])
    lus = lire_archive(archive, 17, {16, 17})

    assert charger(connexion, lus) == {"dossiers": 3, "etapes": 6, "textes": 4}
    assert charger(connexion, lus) == {"dossiers": 0, "etapes": 0, "textes": 0}
    assert connexion.scalar(select(Texte.dossier_id).where(Texte.legislature == 17, Texte.numero == "300")) == "DLR3"
    assert connexion.scalar(select(Etape.chambre).where(Etape.id == "CMP-C")) is None
