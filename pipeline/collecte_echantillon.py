"""Charge l'échantillon officiel de comptes rendus (132 séances, 14e législature).

    uv run python -m pipeline.collecte_echantillon            # télécharge si besoin, puis charge
    uv run python -m pipeline.collecte_echantillon fichier.xml

Premier script de collecte (jalon 1) : il valide le parseur et le schéma sur des données
réelles. Les liaisons aux députés, groupes et dossiers viendront au jalon 2.
"""

import argparse
import logging
from pathlib import Path

from db.connexion import creer_moteur
from pipeline.chargement import Bilan, charger_seance
from pipeline.syceron import lire_fichier
from pipeline.telechargement import telecharger_url

URL_ECHANTILLON = (
    "https://raw.githubusercontent.com/Assemblee-nationale/opendata_snippets/"
    "master/data_src/SyceronBrut.sample.xml"
)
CHEMIN_PAR_DEFAUT = Path("donnees/echantillon/SyceronBrut.sample.xml")

journal = logging.getLogger("pipeline.collecte_echantillon")


def collecter(chemin: Path) -> Bilan:
    bilan = Bilan()
    moteur = creer_moteur()
    for seance in lire_fichier(chemin):
        # Une transaction par séance : une séance en erreur n'annule pas les autres.
        with moteur.begin() as connexion:
            bilan += charger_seance(connexion, seance)
    return bilan


def main(arguments: list[str] | None = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parseur = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parseur.add_argument("fichier", nargs="?", type=Path, default=CHEMIN_PAR_DEFAUT)
    args = parseur.parse_args(arguments)

    if not args.fichier.exists():
        if args.fichier != CHEMIN_PAR_DEFAUT:
            parseur.error(f"fichier introuvable : {args.fichier}")
        telecharger_url(URL_ECHANTILLON, args.fichier)

    bilan = collecter(args.fichier)
    journal.info(
        "%d séances lues, %d interventions insérées ou modifiées",
        bilan.seances,
        bilan.interventions_ecrites,
    )


if __name__ == "__main__":
    main()
