"""Tests de la collecte des scrutins sur une petite archive fictive.

La structure reproduit celle de l'archive Scrutins réelle (vérifiée le 1er novembre 2026).
"""

import json
import zipfile
from pathlib import Path

import pytest
from sqlalchemy import Connection, insert, select

from db.modeles import Appartenance, Depute, Dossier, Groupe, Legislature, Scrutin, Seance, Vote
from pipeline.scrutins import charger, lire_archive


def votants(*deputes: str, delegation: bool = False) -> dict:
    liste = [{"acteurRef": d, "mandatRef": "PM0", "parDelegation": "true" if delegation else "false", "numPlace": "1"} for d in deputes]
    # Un seul votant : l'AN donne un objet au lieu d'une liste.
    return {"votant": liste[0] if len(liste) == 1 else liste}


def scrutin(uid: str, numero: int, groupes: list[dict], **autres) -> dict:
    return {
        "scrutin": {
            "uid": uid,
            "numero": str(numero),
            "seanceRef": autres.get("seance", "S1"),
            "dateScrutin": autres.get("date", "2025-01-15"),
            "typeVote": {"codeTypeVote": autres.get("type", "SPO")},
            "sort": {"code": autres.get("sort", "adopté")},
            "titre": "l'ensemble de la proposition de loi fictive",
            "objet": {"libelle": "l'ensemble de la proposition de loi fictive", "dossierLegislatif": autres.get("dossier")},
            "syntheseVote": {
                "decompte": {"pour": "2", "contre": "1", "abstentions": "0", "nonVotants": "1", "nonVotantsVolontaires": "1"}
            },
            "ventilationVotes": {"organe": {"groupes": {"groupe": groupes}}},
        }
    }


def groupe(organe: str, **positions: dict) -> dict:
    nominatif = {"pours": None, "contres": None, "abstentions": None, "nonVotants": None, **positions}
    return {"organeRef": organe, "vote": {"decompteNominatif": nominatif}}


@pytest.fixture
def archive(tmp_path: Path) -> Path:
    fichiers = {
        "V1": scrutin(
            "V1",
            1,
            [
                groupe("PO1", pours=votants("PA1", "PA2", delegation=True)),
                groupe("PO2", contres=votants("PA3"), nonVotantsVolontaires=votants("PA4")),
            ],
            dossier={"libelle": "Proposition de loi fictive", "dossierRef": "DLR1"},
        ),
        # Défaut réel : plusieurs groupes rangés sous PO0 ; séance et dossier inconnus.
        "V2": scrutin(
            "V2",
            2,
            [groupe("PO0", pours=votants("PA1")), groupe("PO0", contres=votants("PA3")), groupe("PO2", pours=votants("PA9"))],
            seance="S_INCONNUE",
            dossier={"libelle": "Résolution", "dossierRef": "DLR_INCONNU"},
            type="MOC",
            sort="rejeté",
            date="2025-03-10",
        ),
    }
    chemin = tmp_path / "Scrutins.json.zip"
    with zipfile.ZipFile(chemin, "w") as zip_:
        for nom, contenu in fichiers.items():
            zip_.writestr(f"json/{nom}.json", json.dumps(contenu))
    return chemin


@pytest.fixture
def base(connexion: Connection) -> Connection:
    c = connexion
    c.execute(insert(Legislature).values(numero=17, debut="2024-07-01"))
    c.execute(insert(Groupe), [{"id": f"PO{i}", "legislature": 17, "sigle": f"G{i}", "nom": f"Groupe {i}"} for i in (1, 2)])
    c.execute(insert(Depute), [{"id": f"PA{i}", "nom": f"Fictif {i}", "prenom": "X"} for i in (1, 2, 3, 4)])
    c.execute(
        insert(Appartenance),
        [
            {"id": "PM1", "depute_id": "PA1", "groupe_id": "PO1", "qualite": "membre", "debut": "2024-07-19", "fin": None},
            {"id": "PM3", "depute_id": "PA3", "groupe_id": "PO2", "qualite": "membre", "debut": "2024-07-19", "fin": None},
        ],
    )
    c.execute(insert(Dossier).values(id="DLR1", legislature=17, titre_officiel="Proposition de loi fictive", type="proposition"))
    c.execute(insert(Seance).values(id="S1", legislature=17, debut="2025-01-15T15:00:00+01:00"))
    return c


def test_lecture(archive: Path) -> None:
    v1, v2 = lire_archive(archive)

    assert v1.scrutin["type"] == "ordinaire" and v1.scrutin["resultat"] == "adopte"
    assert (v1.scrutin["pour"], v1.scrutin["non_votants"]) == (2, 2)  # non-votants volontaires compris
    assert {(v["depute_id"], v["groupe_id"], v["position"], v["par_delegation"]) for v in v1.votes} == {
        ("PA1", "PO1", "pour", True),
        ("PA2", "PO1", "pour", True),
        ("PA3", "PO2", "contre", False),
        ("PA4", "PO2", "non_votant", False),
    }
    assert (v2.scrutin["type"], v2.scrutin["resultat"]) == ("motion", "rejete")


def test_chargement(base: Connection, archive: Path) -> None:
    bilan = charger(base, lire_archive(archive))

    assert (bilan.scrutins, bilan.votes) == (2, 6)
    assert (bilan.sans_seance, bilan.sans_dossier, bilan.votes_ignores, bilan.groupes_retrouves) == (1, 1, 1, 2)
    liens = dict(base.execute(select(Scrutin.id, Scrutin.seance_id)).all())
    assert liens == {"V1": "S1", "V2": None}
    assert base.scalar(select(Scrutin.dossier_id).where(Scrutin.id == "V1")) == "DLR1"
    # PO0 : le groupe est retrouvé dans les appartenances, à la date du vote.
    groupes_v2 = dict(base.execute(select(Vote.depute_id, Vote.groupe_id).where(Vote.scrutin_id == "V2")).all())
    assert groupes_v2 == {"PA1": "PO1", "PA3": "PO2"}


def test_idempotence(base: Connection, archive: Path) -> None:
    charger(base, lire_archive(archive))
    assert charger(base, lire_archive(archive)).ecritures == {"scrutins": 0, "votes": 0}
