"""Tests du point d'entrée : enchaînement des étapes et enregistrement du run."""

from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, delete, select

from db.modeles import RunPipeline
from pipeline.collecte import EtapeFinie, executer


@pytest.fixture
def runs(moteur: Engine) -> Iterator[Engine]:
    """Les runs sont écrits hors de la transaction du test : on les efface à la fin."""
    yield moteur
    with moteur.begin() as connexion:
        connexion.execute(delete(RunPipeline))


def dernier_run(moteur: Engine) -> RunPipeline:
    with moteur.connect() as connexion:
        return connexion.execute(select(RunPipeline).order_by(RunPipeline.id.desc()).limit(1)).one()


def test_run_reussi(runs: Engine) -> None:
    appels = []

    def etape(nom: str, resultat: EtapeFinie):
        def lancer(legislature: int) -> EtapeFinie:
            appels.append((nom, legislature))
            return resultat

        return (nom, lancer)

    etapes = [
        etape("a", EtapeFinie()),
        etape("b", EtapeFinie(nouveaux=42, avertissements=["CR1.xml : mis de côté"])),
    ]
    assert executer(17, etapes, runs) == "succes"

    assert appels == [("a", 17), ("b", 17)]
    run = dernier_run(runs)
    assert (run.statut, run.nb_nouveaux) == ("succes", 42)
    assert run.fin is not None
    assert run.erreurs == [{"etape": "b", "niveau": "avertissement", "message": "CR1.xml : mis de côté"}]


def test_etape_en_echec_n_arrete_pas_les_suivantes(runs: Engine) -> None:
    suivante = []

    def casse(legislature: int) -> EtapeFinie:
        raise OSError("archive injoignable")

    def apres(legislature: int) -> EtapeFinie:
        suivante.append(legislature)
        return EtapeFinie()

    assert executer(17, [("dossiers", casse), ("liaison", apres)], runs) == "echec"

    assert suivante == [17]
    run = dernier_run(runs)
    assert run.statut == "echec"
    assert run.erreurs == [{"etape": "dossiers", "niveau": "erreur", "message": "OSError : archive injoignable"}]
