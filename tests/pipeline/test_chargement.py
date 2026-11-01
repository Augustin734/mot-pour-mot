"""Tests du chargement en base : idempotence et mise à jour des corrections."""

from dataclasses import replace
from pathlib import Path

from sqlalchemy import Connection, func, select, text

from db.modeles import Intervention, Legislature, PointOdj, Seance
from pipeline.chargement import charger_seance
from pipeline.syceron import lire_fichier

FICHIER = Path(__file__).parent / "donnees" / "comptes_rendus_mini.xml"


def compter(connexion: Connection, modele) -> int:
    return connexion.scalar(select(func.count()).select_from(modele))


def test_chargement_complet(connexion: Connection) -> None:
    for seance in lire_fichier(FICHIER):
        charger_seance(connexion, seance)

    assert compter(connexion, Legislature) == 1
    assert compter(connexion, Seance) == 2
    assert compter(connexion, PointOdj) == 2
    assert compter(connexion, Intervention) == 6
    recherche = connexion.scalar(
        select(Intervention.orateur_libelle).where(
            Intervention.recherche.op("@@")(text("plainto_tsquery('francais', 'jardin partage')"))
        )
    )
    assert recherche == "Mme Alice Exemple"


def test_rechargement_idempotent(connexion: Connection) -> None:
    seance = next(lire_fichier(FICHIER))
    premier = charger_seance(connexion, seance)
    second = charger_seance(connexion, seance)

    assert premier.interventions_ecrites == 5
    assert second.interventions_ecrites == 0  # rien n'a changé : aucune écriture
    assert compter(connexion, Intervention) == 5


def test_correction_mise_a_jour_sans_doublon(connexion: Connection) -> None:
    seance = next(lire_fichier(FICHIER))
    charger_seance(connexion, seance)

    corrigee = replace(seance, interventions=list(seance.interventions))
    corrigee.interventions[0] = replace(corrigee.interventions[0], texte="La séance est reprise.")
    bilan = charger_seance(connexion, corrigee)

    assert bilan.interventions_ecrites == 1
    assert compter(connexion, Intervention) == 5
    assert connexion.scalar(select(Intervention.texte).where(Intervention.ordre == 2)) == (
        "La séance est reprise."
    )
