"""Collecte des dossiers législatifs : dossiers, étapes et textes numérotés.

    uv run python -m pipeline.dossiers                  # 17e législature
    uv run python -m pipeline.dossiers --legislature 16

La table texte est la clé de la liaison séance ↔ loi : elle relie le numéro cité dans les
comptes rendus (bibard, ex. « n° 912 ») à son dossier. Ce numéro est celui des documents
imprimés de l'AN (uid …B0912) ; le texte de la commission reprend le numéro de son rapport
(…BTC0912). Les textes adoptés (…BTA, …TAP) ont leur propre numérotation, qui entrerait en
collision avec la première : ils ne sont pas gardés.

Seuls les dossiers législatifs (les lois) sont chargés en V1 : les propositions de
résolution et les missions de contrôle n'ont pas de type dans le schéma.
"""

import argparse
import json
import logging
import re
import zipfile
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

from sqlalchemy import Connection, select

from db.connexion import creer_moteur
from db.modeles import Dossier, Etape, Legislature, Texte
from pipeline.ecriture import upsert
from pipeline.telechargement import telecharger_archive

journal = logging.getLogger("pipeline.dossiers")

# uid d'un document numéroté de l'AN : PIONANR5L17B0912, RAPPANR5L17B0912, PIONANR5L17BTC0912…
DOCUMENT_NUMEROTE = re.compile(r"^(?P<famille>[A-Z]+)ANR5L(?P<legislature>\d+)B(?P<tc>TC)?(?P<numero>\d+)$")
# Documents de commission : le numéro désigne alors le texte de la commission.
FAMILLES_COMMISSION = {"RAPP", "AVIS"}

# Étapes d'une lecture : préfixe du codeActe → chambre ; suffixe → type d'étape.
PREFIXES_LECTURE = re.compile(r"^(?P<prefixe>AN\d+|SN\d+|ANNLEC|SNNLEC|ANLUNI|ANLDEF)-(?P<suffixe>DEPOT|COM|DEBATS)$")
TYPES_PAR_SUFFIXE = {"DEPOT": "depot", "COM": "commission", "DEBATS": "seance"}
ETAPES_CMP = {"CMP-COM": ("cmp", None), "CMP-DEBATS-AN": ("seance", "an"), "CMP-DEBATS-SN": ("seance", "senat")}


@dataclass
class Dossiers:
    dossiers: list[dict] = field(default_factory=list)
    etapes: list[dict] = field(default_factory=list)
    textes: list[dict] = field(default_factory=list)
    ignores: dict[str, int] = field(default_factory=dict)  # textes non gardés, par raison

    def ignorer(self, raison: str) -> None:
        self.ignores[raison] = self.ignores.get(raison, 0) + 1


def _liste(valeur: dict | list | None) -> list:
    """Le JSON de l'AN donne un objet seul au lieu d'une liste quand il n'y a qu'un élément."""
    if valeur is None:
        return []
    return valeur if isinstance(valeur, list) else [valeur]


def _actes(conteneur: dict | None) -> Iterator[dict]:
    """Parcourt l'arbre des actes législatifs en profondeur."""
    for acte in _liste((conteneur or {}).get("acteLegislatif")):
        yield acte
        yield from _actes(acte.get("actesLegislatifs"))


def _instant(valeur: str | None) -> datetime | None:
    return datetime.fromisoformat(valeur) if valeur else None


def _date_acte(acte: dict) -> datetime | None:
    """Date de l'acte, ou à défaut la plus ancienne de ses sous-actes (une étape n'a pas de date propre)."""
    if acte.get("dateActe"):
        return _instant(acte["dateActe"])
    dates = [_instant(a["dateActe"]) for a in _actes(acte.get("actesLegislatifs")) if a.get("dateActe")]
    return min(dates, default=None)


def type_etape(code_acte: str) -> tuple[str, str | None] | None:
    """(type, chambre) d'un acte, ou None s'il n'est pas une étape de la frise."""
    if code_acte == "PROM-PUB":
        return "promulgation", None
    if code_acte in ETAPES_CMP:
        return ETAPES_CMP[code_acte]
    if m := PREFIXES_LECTURE.match(code_acte):
        prefixe, suffixe = m["prefixe"], m["suffixe"]
        type_ = "lecture_definitive" if prefixe == "ANLDEF" and suffixe == "DEBATS" else TYPES_PAR_SUFFIXE[suffixe]
        return type_, "an" if prefixe.startswith("AN") else "senat"
    return None


def lire_dossier(brut: dict) -> tuple[dict, list[dict]]:
    actes = list(_actes(brut.get("actesLegislatifs")))
    depots = sorted(
        (a for a in actes if a["@xsi:type"] == "DepotInitiative_Type" and a.get("dateActe")),
        key=lambda a: a["dateActe"],
    )
    # Projet ou proposition : d'après le premier texte déposé (PRJL… ou PION…), le libellé
    # de procédure étant ambigu (« Projet ou proposition de loi organique »).
    initial = depots[0].get("texteAssocie", "") if depots else ""
    if initial.startswith("PRJL"):
        type_ = "projet"
    elif initial.startswith("PION"):
        type_ = "proposition"
    else:
        type_ = "projet" if brut["procedureParlementaire"]["libelle"].startswith("Projet") else "proposition"

    types_actes = {a["@xsi:type"] for a in actes}
    if "Promulgation_Type" in types_actes:
        statut = "adopte"
    elif "RetraitInitiative_Type" in types_actes:
        statut = "retire"
    else:
        # Un rejet n'est pas déduit : en première lecture, il ne clôt pas la navette.
        statut = "en_cours"

    dates = [_instant(a["dateActe"]) for a in actes if a.get("dateActe")]
    dossier = {
        "id": brut["uid"],
        "legislature": int(brut["legislature"]),
        "titre_officiel": brut["titreDossier"]["titre"],
        "type": type_,
        "statut": statut,
        "date_depot": _instant(depots[0]["dateActe"]).date() if depots else None,
        "date_derniere_activite": max(dates, default=None),
    }
    etapes = []
    for acte in actes:
        if (etape := type_etape(acte["codeActe"])) is None:
            continue
        instant = _date_acte(acte)
        etapes.append(
            {
                "id": acte["uid"],
                "dossier_id": brut["uid"],
                "type": etape[0],
                "chambre": etape[1],
                "date": instant.date() if instant else None,
            }
        )
    return dossier, etapes


def lire_archive(chemin: Path, legislature: int, legislatures_connues: set[int]) -> Dossiers:
    resultat = Dossiers()
    documents = []
    with zipfile.ZipFile(chemin) as archive:
        for nom in archive.namelist():
            if not nom.endswith(".json"):
                continue
            contenu = json.loads(archive.read(nom))
            if brut := contenu.get("dossierParlementaire"):
                if brut.get("@xsi:type") != "DossierLegislatif_Type":
                    continue
                if int(brut["legislature"]) not in legislatures_connues:
                    # Quelques dossiers très anciens (8e, 11e) : pas de législature en base.
                    journal.info("Dossier %s : législature %s inconnue, ignoré", brut["uid"], brut["legislature"])
                    continue
                dossier, etapes = lire_dossier(brut)
                resultat.dossiers.append(dossier)
                resultat.etapes.extend(etapes)
            elif document := contenu.get("document"):
                documents.append(document)

    dossiers = {d["id"] for d in resultat.dossiers}
    textes: dict[str, dict] = {}
    for document in documents:
        m = DOCUMENT_NUMEROTE.match(document["uid"])
        if not m or int(m["legislature"]) != legislature:
            continue  # textes adoptés, documents du Sénat ou d'une autre législature
        if document.get("dossierRef") not in dossiers:
            resultat.ignorer("dossier non chargé (résolution, mission…)" if document.get("dossierRef") else "sans dossier")
            continue
        numero = str(int(m["numero"]))  # « 0912 » → « 912 », comme le bibard nettoyé
        commission = m["tc"] is not None or m["famille"] in FAMILLES_COMMISSION
        texte = textes.setdefault(
            numero,
            {"legislature": legislature, "numero": numero, "dossier_id": document["dossierRef"], "type": "depose"},
        )
        if commission:
            texte["type"] = "commission"
        if texte["dossier_id"] != document["dossierRef"]:
            journal.warning("Texte n° %s rattaché à deux dossiers : %s gardé", numero, texte["dossier_id"])
    resultat.textes = list(textes.values())
    return resultat


def charger(connexion: Connection, lus: Dossiers) -> dict[str, int]:
    """Écrit les dossiers, puis leurs étapes et textes. Renvoie les lignes écrites."""
    return {
        "dossiers": upsert(connexion, Dossier.__table__, lus.dossiers, ["id"]),
        "etapes": upsert(connexion, Etape.__table__, lus.etapes, ["id"]),
        "textes": upsert(connexion, Texte.__table__, lus.textes, ["legislature", "numero"]),
    }


def collecter(legislature: int) -> dict[str, int]:
    """Télécharge, lit et charge les dossiers ; renvoie les lignes écrites par table."""
    archive = telecharger_archive("dossiers", legislature)
    with creer_moteur().begin() as connexion:
        # Les législatures viennent du jeu « acteurs et organes », à charger avant.
        connues = set(connexion.scalars(select(Legislature.numero)))
        lus = lire_archive(archive.chemin, legislature, connues)
        ecrites = charger(connexion, lus)
    journal.info(
        "%d dossiers, %d étapes, %d textes lus ; lignes insérées ou modifiées : %s ; textes ignorés : %s",
        len(lus.dossiers),
        len(lus.etapes),
        len(lus.textes),
        ecrites,
        lus.ignores,
    )
    return ecrites


def main(arguments: list[str] | None = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parseur = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parseur.add_argument("--legislature", type=int, default=17)
    args = parseur.parse_args(arguments)
    collecter(args.legislature)


if __name__ == "__main__":
    main()
