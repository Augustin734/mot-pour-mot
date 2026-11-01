"""Collecte des scrutins publics et des votes nominatifs.

    uv run python -m pipeline.scrutins                  # 17e législature
    uv run python -m pipeline.scrutins --legislature 16

L'archive contient un fichier JSON par scrutin, avec la ventilation des votes par groupe
et le vote de chaque député (environ 1,4 million de votes pour la 17e). Les scrutins sont
lus un par un et écrits par paquets, pour ne pas tout garder en mémoire.

Le groupe d'un vote est celui sous lequel l'AN le range dans la ventilation : c'est le
groupe du député au moment du vote, publié par l'AN. Seule exception : quelques scrutins
(décembre 2024 surtout) rangent plusieurs groupes sous un identifiant inexistant (PO0) ;
le groupe est alors retrouvé dans les appartenances, à la date du vote.
Les mises au point (un député qui déclare après coup avoir voulu voter autrement) ne
modifient pas le vote officiel et ne sont pas chargées en V1.

À lancer après les acteurs, les dossiers et les comptes rendus : un lien vers une séance
ou un dossier absents de la base est laissé vide, puis rempli à un run suivant.
"""

import argparse
import json
import logging
import zipfile
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from sqlalchemy import Connection, select

from db.connexion import creer_moteur
from db.modeles import Appartenance, Depute, Dossier, Groupe, Scrutin, Seance, Vote
from pipeline.ecriture import upsert
from pipeline.telechargement import telecharger_archive

journal = logging.getLogger("pipeline.scrutins")

TYPES = {"SPO": "ordinaire", "SPS": "solennel", "MOC": "motion"}
RESULTATS = {"adopté": "adopte", "rejeté": "rejete"}
POSITIONS = {
    "pours": "pour",
    "contres": "contre",
    "abstentions": "abstention",
    "nonVotants": "non_votant",
    "nonVotantsVolontaires": "non_votant",
}
# Scrutins lus avant chaque écriture : quelques dizaines de milliers de votes à la fois.
SCRUTINS_PAR_PAQUET = 200


@dataclass
class ScrutinLu:
    scrutin: dict
    votes: list[dict]


@dataclass
class BilanScrutins:
    scrutins: int = 0
    votes: int = 0
    ecritures: dict[str, int] = field(default_factory=lambda: {"scrutins": 0, "votes": 0})
    sans_seance: int = 0
    sans_dossier: int = 0
    votes_ignores: int = 0  # député absent de la base
    groupes_retrouves: int = 0  # groupe inconnu dans la ventilation, retrouvé par la date


def _liste(valeur: dict | list | None) -> list:
    """Le JSON de l'AN donne un objet seul au lieu d'une liste quand il n'y a qu'un élément."""
    if valeur is None:
        return []
    return valeur if isinstance(valeur, list) else [valeur]


def lire_scrutin(brut: dict) -> ScrutinLu:
    decompte = brut["syntheseVote"]["decompte"]
    reference = brut["objet"].get("dossierLegislatif") or {}
    scrutin = {
        "id": brut["uid"],
        "seance_id": brut.get("seanceRef"),
        "dossier_id": reference.get("dossierRef"),
        "numero": int(brut["numero"]),
        "date": date.fromisoformat(brut["dateScrutin"]),
        "objet": brut["objet"]["libelle"] or brut["titre"],
        "type": TYPES[brut["typeVote"]["codeTypeVote"]],
        "resultat": RESULTATS[brut["sort"]["code"]],
        "pour": int(decompte["pour"]),
        "contre": int(decompte["contre"]),
        "abstentions": int(decompte["abstentions"]),
        "non_votants": int(decompte["nonVotants"]) + int(decompte.get("nonVotantsVolontaires") or 0),
    }
    votes = []
    for groupe in _liste(brut["ventilationVotes"]["organe"]["groupes"]["groupe"]):
        for cle, bloc in (groupe["vote"].get("decompteNominatif") or {}).items():
            for votant in _liste((bloc or {}).get("votant")):
                votes.append(
                    {
                        "scrutin_id": brut["uid"],
                        "depute_id": votant["acteurRef"],
                        "groupe_id": groupe["organeRef"],
                        "position": POSITIONS[cle],
                        "par_delegation": votant.get("parDelegation") == "true",
                    }
                )
    return ScrutinLu(scrutin, votes)


def lire_archive(chemin: Path) -> Iterator[ScrutinLu]:
    with zipfile.ZipFile(chemin) as archive:
        for nom in sorted(archive.namelist()):
            if nom.endswith(".json"):
                yield lire_scrutin(json.loads(archive.read(nom))["scrutin"])


def charger(connexion: Connection, lus: Iterator[ScrutinLu]) -> BilanScrutins:
    """Écrit les scrutins et leurs votes par paquets. Les liens vers une séance, un dossier
    ou un député absents de la base sont laissés vides (ou le vote ignoré) et comptés."""
    seances = set(connexion.scalars(select(Seance.id)))
    dossiers = set(connexion.scalars(select(Dossier.id)))
    deputes = set(connexion.scalars(select(Depute.id)))
    groupes = set(connexion.scalars(select(Groupe.id)))
    mandats: dict[str, list[tuple]] = {}
    for depute_id, groupe_id, debut, fin in connexion.execute(
        select(Appartenance.depute_id, Appartenance.groupe_id, Appartenance.debut, Appartenance.fin)
    ):
        mandats.setdefault(depute_id, []).append((groupe_id, debut, fin))
    bilan = BilanScrutins()

    def groupe_a_la_date(depute_id: str, jour: date) -> str | None:
        for groupe_id, debut, fin in mandats.get(depute_id, []):
            if debut <= jour and (fin is None or jour <= fin):
                return groupe_id
        return None

    def ecrire(paquet: list[ScrutinLu]) -> None:
        scrutins, votes = [], []
        for lu in paquet:
            scrutin = dict(lu.scrutin)
            if scrutin["seance_id"] not in seances:
                scrutin["seance_id"] = None
                bilan.sans_seance += 1
            if scrutin["dossier_id"] not in dossiers:
                scrutin["dossier_id"] = None
                bilan.sans_dossier += 1
            scrutins.append(scrutin)
            for vote in lu.votes:
                if vote["depute_id"] not in deputes:
                    bilan.votes_ignores += 1
                    continue
                if vote["groupe_id"] not in groupes:
                    vote = {**vote, "groupe_id": groupe_a_la_date(vote["depute_id"], scrutin["date"])}
                    bilan.groupes_retrouves += 1
                votes.append(vote)
        bilan.scrutins += len(scrutins)
        bilan.votes += len(votes)
        bilan.ecritures["scrutins"] += upsert(connexion, Scrutin.__table__, scrutins, ["id"])
        bilan.ecritures["votes"] += upsert(connexion, Vote.__table__, votes, ["scrutin_id", "depute_id"])

    paquet: list[ScrutinLu] = []
    for lu in lus:
        paquet.append(lu)
        if len(paquet) == SCRUTINS_PAR_PAQUET:
            ecrire(paquet)
            paquet = []
    ecrire(paquet)
    return bilan


def main(arguments: list[str] | None = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parseur = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parseur.add_argument("--legislature", type=int, default=17)
    args = parseur.parse_args(arguments)

    archive = telecharger_archive("scrutins", args.legislature)
    with creer_moteur().begin() as connexion:
        bilan = charger(connexion, lire_archive(archive.chemin))
    journal.info(
        "%d scrutins, %d votes ; lignes insérées ou modifiées : %s ; "
        "%d scrutins sans séance connue, %d sans dossier connu, %d votes de députés inconnus ignorés, "
        "%d groupes retrouvés par la date",
        bilan.scrutins,
        bilan.votes,
        bilan.ecritures,
        bilan.sans_seance,
        bilan.sans_dossier,
        bilan.votes_ignores,
        bilan.groupes_retrouves,
    )


if __name__ == "__main__":
    main()
