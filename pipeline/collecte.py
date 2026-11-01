"""Collecte complète d'une législature : enchaîne toutes les étapes du pipeline.

    uv run python -m pipeline.collecte                  # 17e législature
    uv run python -m pipeline.collecte --legislature 16

C'est le point d'entrée du futur run de nuit (Planificateur de tâches Windows, jalon 8).
Ordre : acteurs et organes, dossiers, comptes rendus, scrutins, puis liaison ; chaque
étape s'appuie sur les précédentes.

Chaque run est enregistré dans run_pipeline (début, fin, statut, erreurs, nombre
d'interventions nouvelles ou modifiées), que l'API expose sur /api/v1/statut. Une étape
en échec n'arrête pas les suivantes : toutes sont idempotentes et travaillent avec les
données déjà en base. Le run est alors marqué en échec et le code de sortie vaut 1.
"""

import argparse
import logging
from collections.abc import Callable
from dataclasses import dataclass, field

from sqlalchemy import Engine, func, insert, update

from db.connexion import creer_moteur
from db.modeles import RunPipeline
from pipeline import acteurs_organes, comptes_rendus, dossiers, liaison, scrutins

journal = logging.getLogger("pipeline.collecte")


@dataclass
class EtapeFinie:
    nouveaux: int = 0  # interventions insérées ou modifiées
    avertissements: list[str] = field(default_factory=list)
    erreurs: list[str] = field(default_factory=list)


def _comptes_rendus(legislature: int) -> EtapeFinie:
    bilan, mis_de_cote, erreurs = comptes_rendus.collecter(legislature)
    return EtapeFinie(
        nouveaux=bilan.interventions_ecrites,
        avertissements=[f"{nom} : mis de côté (compte rendu provisoire invalide)" for nom in mis_de_cote],
        erreurs=[f"{nom} : séance non chargée" for nom in erreurs],
    )


def _sans_bilan(collecter: Callable[[int], object]) -> Callable[[int], EtapeFinie]:
    def etape(legislature: int) -> EtapeFinie:
        collecter(legislature)
        return EtapeFinie()

    return etape


ETAPES: list[tuple[str, Callable[[int], EtapeFinie]]] = [
    ("acteurs_organes", _sans_bilan(acteurs_organes.collecter)),
    ("dossiers", _sans_bilan(dossiers.collecter)),
    ("comptes_rendus", _comptes_rendus),
    ("scrutins", _sans_bilan(scrutins.collecter)),
    ("liaison", _sans_bilan(liaison.collecter)),
]


def executer(
    legislature: int,
    etapes: list[tuple[str, Callable[[int], EtapeFinie]]] = ETAPES,
    moteur: Engine | None = None,
) -> str:
    """Lance les étapes et enregistre le run ; renvoie son statut (succes ou echec)."""
    moteur = moteur or creer_moteur()
    # Le run est créé dans sa propre transaction : il reste visible même si tout échoue.
    with moteur.begin() as connexion:
        run_id = connexion.scalar(insert(RunPipeline).values(statut="en_cours").returning(RunPipeline.id))

    nouveaux, problemes = 0, []
    for nom, etape in etapes:
        journal.info("Étape %s", nom)
        try:
            resultat = etape(legislature)
        except Exception as erreur:
            journal.exception("Étape %s en échec", nom)
            problemes.append({"etape": nom, "niveau": "erreur", "message": f"{type(erreur).__name__} : {erreur}"})
            continue
        nouveaux += resultat.nouveaux
        problemes += [{"etape": nom, "niveau": "avertissement", "message": m} for m in resultat.avertissements]
        problemes += [{"etape": nom, "niveau": "erreur", "message": m} for m in resultat.erreurs]

    statut = "echec" if any(p["niveau"] == "erreur" for p in problemes) else "succes"
    with moteur.begin() as connexion:
        connexion.execute(
            update(RunPipeline)
            .where(RunPipeline.id == run_id)
            .values(fin=func.now(), statut=statut, erreurs=problemes or None, nb_nouveaux=nouveaux)
        )
    journal.info("Run %d : %s, %d interventions nouvelles ou modifiées, %d problèmes", run_id, statut, nouveaux, len(problemes))
    return statut


def main(arguments: list[str] | None = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parseur = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parseur.add_argument("--legislature", type=int, default=17)
    args = parseur.parse_args(arguments)
    if executer(args.legislature) != "succes":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
