"""Collecte du jeu « acteurs et organes » : législatures, groupes, députés, appartenances.

    uv run python -m pipeline.acteurs_organes                  # 17e législature
    uv run python -m pipeline.acteurs_organes --legislature 16

Source : l'archive AMO30 (tous les acteurs, tous les mandats, historique), un fichier JSON
par acteur et par organe. Seuls les groupes et les députés de la législature demandée sont
gardés ; les législatures sont toutes chargées (une ligne chacune).
"""

import argparse
import csv
import json
import logging
import zipfile
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from sqlalchemy import Connection

from db.connexion import creer_moteur
from db.modeles import Appartenance, Depute, Groupe, Legislature
from pipeline.ecriture import upsert
from pipeline.telechargement import telecharger_archive

FICHIER_ORDRE = Path(__file__).parent / "reference" / "ordre_hemicycle.csv"

# Libellés AN (infosQualite.codeQualite) des mandats de groupe → valeurs du schéma.
QUALITES = {
    "Membre": "membre",
    "Membre apparenté": "apparente",
    "Président": "president",
    "Député non-inscrit": "non_inscrit",
}

journal = logging.getLogger("pipeline.acteurs_organes")


@dataclass
class Referentiel:
    legislatures: list[dict] = field(default_factory=list)
    groupes: list[dict] = field(default_factory=list)
    deputes: list[dict] = field(default_factory=list)
    appartenances: list[dict] = field(default_factory=list)


def _liste(valeur: dict | list | None) -> list:
    """Le JSON de l'AN donne un objet seul au lieu d'une liste quand il n'y a qu'un élément."""
    if valeur is None:
        return []
    return valeur if isinstance(valeur, list) else [valeur]


def _texte(valeur: dict | str) -> str:
    """Certains identifiants sont des objets typés : {"@xsi:type": …, "#text": "PA…"}."""
    return valeur["#text"] if isinstance(valeur, dict) else valeur


def _date(valeur: str | None) -> date | None:
    return date.fromisoformat(valeur) if valeur else None


def circonscription(lieu: dict) -> str | None:
    """« Bas-Rhin (6e) », « Paris (1re) »."""
    if not lieu.get("departement"):
        return None
    numero = lieu.get("numCirco")
    if not numero:
        return lieu["departement"]
    return f"{lieu['departement']} ({numero}{'re' if numero == '1' else 'e'})"


def lire_ordre_hemicycle(chemin: Path, legislature: int) -> dict[str, int]:
    with chemin.open(encoding="utf-8") as fichier:
        lignes = csv.DictReader(ligne for ligne in fichier if not ligne.startswith("#"))
        return {
            ligne["groupe_id"]: int(ligne["ordre_hemicycle"])
            for ligne in lignes
            if int(ligne["legislature"]) == legislature
        }


def lire_archive(chemin: Path, legislature: int, ordre: dict[str, int]) -> Referentiel:
    organes, acteurs = [], []
    with zipfile.ZipFile(chemin) as archive:
        for nom in archive.namelist():
            if not nom.endswith(".json"):
                continue
            contenu = json.loads(archive.read(nom))
            if "organe" in contenu:
                organes.append(contenu["organe"])
            elif "acteur" in contenu:
                acteurs.append(contenu["acteur"])
            # Les autres fichiers (déports d'intérêts) ne servent pas en V1.

    ref = Referentiel()
    for organe in organes:
        periode = organe["viMoDe"]
        if organe["codeType"] == "ASSEMBLEE":
            ref.legislatures.append(
                {
                    "numero": int(organe["legislature"]),
                    "debut": _date(periode["dateDebut"]),
                    "fin": _date(periode["dateFin"]),
                }
            )
        elif organe["codeType"] == "GP" and organe.get("legislature") == str(legislature):
            ref.groupes.append(
                {
                    "id": organe["uid"],
                    "legislature": legislature,
                    "sigle": organe["libelleAbrev"],
                    "nom": organe["libelle"],
                    "couleur": organe.get("couleurAssociee"),
                    "ordre_hemicycle": ordre.get(organe["uid"]),
                }
            )
    groupes = {g["id"] for g in ref.groupes}
    for g in ref.groupes:
        if g["ordre_hemicycle"] is None:
            journal.warning(
                "Groupe %s (%s) absent de %s : ajouter son rang", g["id"], g["sigle"], FICHIER_ORDRE.name
            )

    for acteur in acteurs:
        mandats = [
            m for m in _liste(acteur["mandats"]["mandat"]) if m.get("legislature") == str(legislature)
        ]
        sieges = sorted(
            (m for m in mandats if m["typeOrgane"] == "ASSEMBLEE"), key=lambda m: m["dateDebut"]
        )
        if not sieges:
            continue  # ministre non député, ancien député d'une autre législature…
        identifiant = _texte(acteur["uid"])
        identite = acteur["etatCivil"]["ident"]
        ref.deputes.append(
            {
                "id": identifiant,
                "nom": identite["nom"],
                "prenom": identite["prenom"],
                # Le dernier mandat : un député réélu après une annulation change de mandat.
                "circonscription": circonscription(sieges[-1]["election"]["lieu"]),
            }
        )
        for mandat in mandats:
            if mandat["typeOrgane"] != "GP":
                continue
            groupe_id = mandat["organes"]["organeRef"]
            if groupe_id not in groupes:
                journal.warning("Mandat %s : groupe %s inconnu, ignoré", mandat["uid"], groupe_id)
                continue
            libelle = mandat["infosQualite"]["codeQualite"]
            if libelle not in QUALITES:
                # Échec explicite : un nouveau libellé doit être classé à la main.
                raise ValueError(f"Mandat {mandat['uid']} : qualité inconnue « {libelle} »")
            ref.appartenances.append(
                {
                    "id": mandat["uid"],
                    "depute_id": identifiant,
                    "groupe_id": groupe_id,
                    "qualite": QUALITES[libelle],
                    "debut": _date(mandat["dateDebut"]),
                    "fin": _date(mandat["dateFin"]),
                }
            )
    return ref


def charger(connexion: Connection, ref: Referentiel) -> dict[str, int]:
    """Écrit le référentiel (dans l'ordre des clés étrangères). Renvoie les lignes écrites."""
    return {
        "legislatures": upsert(connexion, Legislature.__table__, ref.legislatures, ["numero"]),
        "groupes": upsert(connexion, Groupe.__table__, ref.groupes, ["id"]),
        "deputes": upsert(connexion, Depute.__table__, ref.deputes, ["id"]),
        "appartenances": upsert(connexion, Appartenance.__table__, ref.appartenances, ["id"]),
    }


def main(arguments: list[str] | None = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parseur = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parseur.add_argument("--legislature", type=int, default=17)
    args = parseur.parse_args(arguments)

    archive = telecharger_archive("acteurs_organes", args.legislature)
    ref = lire_archive(archive.chemin, args.legislature, lire_ordre_hemicycle(FICHIER_ORDRE, args.legislature))
    with creer_moteur().begin() as connexion:
        ecrites = charger(connexion, ref)
    journal.info(
        "%d groupes, %d députés, %d appartenances lus ; lignes insérées ou modifiées : %s",
        len(ref.groupes),
        len(ref.deputes),
        len(ref.appartenances),
        ecrites,
    )


if __name__ == "__main__":
    main()
