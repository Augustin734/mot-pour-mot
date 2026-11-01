"""Téléchargement des archives de l'open data AN, avec un cache local.

    uv run python -m pipeline.telechargement                 # 17e législature
    uv run python -m pipeline.telechargement --legislature 16

Chaque archive est gardée dans donnees/brut/<législature>/, avec à côté la date
Last-Modified renvoyée par le serveur. Au téléchargement suivant, elle est renvoyée dans
If-Modified-Since : si l'archive n'a pas changé, le serveur répond 304 sans rien envoyer.
Le run de nuit (jalon 8) ne retraitera donc que les jeux de données modifiés.

Le site de l'AN répond depuis plusieurs serveurs qui n'ont pas toujours la même copie
(même contenu, mais dates et ETag différents, constaté le 1er novembre 2026). D'où deux
choix : la date plutôt que l'ETag (une copie plus ancienne ou identique donne 304, alors
qu'un ETag différent forcerait un téléchargement), et une comparaison du contenu reçu
avec le cache (SHA-256) pour ne pas signaler comme modifiée une archive identique.
"""

import argparse
import hashlib
import http.client
import json
import logging
import time
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path

URL_DEPOT = "https://data.assemblee-nationale.fr/static/openData/repository/{legislature}/"

# Chemins vérifiés le 1er novembre 2026 sur la 17e législature (même arborescence pour la 16e).
ARCHIVES = {
    # Tous les acteurs (ministres compris), avec l'historique daté des mandats de groupe.
    "acteurs_organes": "amo/tous_acteurs_mandats_organes_xi_legislature/"
    "AMO30_tous_acteurs_tous_mandats_tous_organes_historique.json.zip",
    "dossiers": "loi/dossiers_legislatifs/Dossiers_Legislatifs.json.zip",
    "scrutins": "loi/scrutins/Scrutins.json.zip",
    "comptes_rendus": "vp/syceronbrut/syseron.xml.zip",
}

RACINE_CACHE = Path("donnees/brut")
DELAI_SECONDES = 120
# Les coupures observées sont passagères : quelques tentatives espacées suffisent.
TENTATIVES = 3
PAUSE_SECONDES = 10

journal = logging.getLogger("pipeline.telechargement")


@dataclass
class Telechargement:
    chemin: Path
    modifie: bool  # False si le cache était à jour (304, ou contenu identique)


def url_archive(nom: str, legislature: int) -> str:
    return URL_DEPOT.format(legislature=legislature) + ARCHIVES[nom]


def _chemin_meta(destination: Path) -> Path:
    return destination.with_name(destination.name + ".meta.json")


def telecharger_url(url: str, destination: Path) -> Telechargement:
    """Télécharge url vers destination, sauf si la copie en cache est encore à jour.

    Une erreur réseau, une erreur 5xx ou un fichier tronqué déclenchent une nouvelle
    tentative ; une erreur 4xx (URL fausse) est remontée tout de suite.
    """
    for tentative in range(1, TENTATIVES + 1):
        try:
            return _telecharger_une_fois(url, destination)
        except urllib.error.HTTPError as erreur:
            if erreur.code < 500 or tentative == TENTATIVES:
                raise
            cause = erreur
        # IncompleteRead (connexion coupée en cours de lecture) n'est pas une OSError.
        except (OSError, http.client.HTTPException) as erreur:
            if tentative == TENTATIVES:
                raise
            cause = erreur
        journal.warning("%s : tentative %d échouée (%s)", destination.name, tentative, cause)
        time.sleep(PAUSE_SECONDES * tentative)
    raise AssertionError("inatteignable")


def _empreinte(chemin: Path) -> str:
    sha = hashlib.sha256()
    with chemin.open("rb") as fichier:
        while bloc := fichier.read(1 << 20):
            sha.update(bloc)
    return sha.hexdigest()


def _telecharger_une_fois(url: str, destination: Path) -> Telechargement:
    meta = _chemin_meta(destination)
    entetes = {}
    if destination.exists() and meta.exists():
        connu = json.loads(meta.read_text())
        # Pas les deux à la fois : If-None-Match l'emporterait sur la date (RFC 9110).
        if connu.get("last_modified"):
            entetes["If-Modified-Since"] = connu["last_modified"]
        elif connu.get("etag"):
            entetes["If-None-Match"] = connu["etag"]

    try:
        reponse = urllib.request.urlopen(urllib.request.Request(url, headers=entetes), timeout=DELAI_SECONDES)
    except urllib.error.HTTPError as erreur:
        if erreur.code == 304:
            journal.info("%s : déjà à jour", destination.name)
            return Telechargement(destination, modifie=False)
        raise

    destination.parent.mkdir(parents=True, exist_ok=True)
    # Écriture dans un fichier temporaire puis renommage : une coupure en cours de route
    # ne remplace jamais une archive valide par un fichier tronqué.
    temporaire = destination.with_name(destination.name + ".partiel")
    with reponse, temporaire.open("wb") as fichier:
        while bloc := reponse.read(1 << 20):
            fichier.write(bloc)
    attendu = reponse.headers.get("Content-Length")
    if attendu is not None and temporaire.stat().st_size != int(attendu):
        temporaire.unlink()
        raise OSError(f"{url} : téléchargement incomplet")
    if destination.suffix == ".zip" and not zipfile.is_zipfile(temporaire):
        temporaire.unlink()
        raise OSError(f"{url} : le fichier reçu n'est pas une archive zip")

    identique = destination.exists() and _empreinte(temporaire) == _empreinte(destination)
    temporaire.replace(destination)
    meta.write_text(
        json.dumps(
            {
                "url": url,
                "etag": reponse.headers.get("ETag"),
                "last_modified": reponse.headers.get("Last-Modified"),
            },
            indent=2,
        )
    )
    if identique:
        journal.info("%s : contenu identique au cache", destination.name)
        return Telechargement(destination, modifie=False)
    journal.info("%s : téléchargé (%.1f Mo)", destination.name, destination.stat().st_size / 1e6)
    return Telechargement(destination, modifie=True)


def telecharger_archive(nom: str, legislature: int, racine: Path = RACINE_CACHE) -> Telechargement:
    destination = racine / str(legislature) / Path(ARCHIVES[nom]).name
    return telecharger_url(url_archive(nom, legislature), destination)


def main(arguments: list[str] | None = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parseur = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parseur.add_argument("--legislature", type=int, default=17)
    parseur.add_argument("archives", nargs="*", help=f"parmi {', '.join(ARCHIVES)} (toutes par défaut)")
    args = parseur.parse_args(arguments)
    if inconnues := set(args.archives) - ARCHIVES.keys():
        parseur.error(f"archive inconnue : {', '.join(sorted(inconnues))}")

    for nom in args.archives or ARCHIVES:
        telecharger_archive(nom, args.legislature)


if __name__ == "__main__":
    main()
