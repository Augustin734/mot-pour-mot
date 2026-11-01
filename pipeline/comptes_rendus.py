"""Collecte des comptes rendus de séance publique d'une législature.

    uv run python -m pipeline.comptes_rendus                  # 17e législature
    uv run python -m pipeline.comptes_rendus --legislature 16

L'archive contient un fichier XML par séance (CRSANR….xml). Chaque séance est chargée
dans sa propre transaction : une séance en erreur est journalisée sans annuler les autres.

Un compte rendu invalide (ex. version provisoire dont les paragraphes ont des rangs en
double) est mis de côté sans être chargé : la version corrigée sera chargée à un run
suivant. Renuméroter soi-même laisserait des lignes obsolètes après la correction.
"""

import argparse
import logging
import zipfile

from db.connexion import creer_moteur
from pipeline.chargement import Bilan, charger_seance
from pipeline.syceron import CompteRenduInvalide, lire_xml
from pipeline.telechargement import telecharger_archive

journal = logging.getLogger("pipeline.comptes_rendus")


def collecter(legislature: int) -> tuple[Bilan, list[str], list[str]]:
    """Renvoie le bilan, les fichiers mis de côté (invalides) et les fichiers en erreur."""
    archive = telecharger_archive("comptes_rendus", legislature)
    bilan, mis_de_cote, erreurs = Bilan(), [], []
    moteur = creer_moteur()
    with zipfile.ZipFile(archive.chemin) as zip_:
        for nom in sorted(n for n in zip_.namelist() if n.endswith(".xml")):
            try:
                with moteur.begin() as connexion:
                    for seance in lire_xml(zip_.read(nom)):
                        bilan += charger_seance(connexion, seance)
            except CompteRenduInvalide as raison:
                journal.warning("%s : mis de côté (%s)", nom, raison)
                mis_de_cote.append(nom)
            except Exception:
                journal.exception("%s : séance non chargée", nom)
                erreurs.append(nom)
    journal.info(
        "%d séances lues, %d interventions insérées ou modifiées, %d mises de côté, %d en erreur",
        bilan.seances,
        bilan.interventions_ecrites,
        len(mis_de_cote),
        len(erreurs),
    )
    return bilan, mis_de_cote, erreurs


def main(arguments: list[str] | None = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parseur = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parseur.add_argument("--legislature", type=int, default=17)
    args = parseur.parse_args(arguments)

    _, _, erreurs = collecter(args.legislature)
    if erreurs:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
