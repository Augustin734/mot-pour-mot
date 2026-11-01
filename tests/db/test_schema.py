"""Tests du schéma : migrations, contraintes et recherche plein texte.

Les données sont fictives (charte de neutralité : aucun propos réel inventé).
"""

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import Connection, Engine, insert, select, text, update
from sqlalchemy.exc import IntegrityError

from db.modeles import Argument, Base, Dossier, Intervention, Legislature, Seance, Texte
from tests.conftest import config_alembic


@pytest.fixture
def donnees_minimales(connexion: Connection) -> Connection:
    connexion.execute(insert(Legislature).values(numero=17, debut="2024-07-18"))
    connexion.execute(
        insert(Dossier).values(
            id="DLR_TEST_1",
            legislature=17,
            titre_officiel="Projet de loi relatif à la protection des forêts",
            alias=["loi Martin"],
            type="projet",
        )
    )
    connexion.execute(
        insert(Seance).values(id="RUANR_TEST_1", legislature=17, debut="2026-10-14T15:00:00+02:00")
    )
    return connexion


def test_migrations_aller_retour(url_test: str) -> None:
    """Le downgrade complet puis l'upgrade fonctionnent : la migration est réversible."""
    config = config_alembic(url_test)
    command.downgrade(config, "base")
    command.upgrade(config, "head")


def test_modeles_conformes_a_la_base(moteur: Engine) -> None:
    """Les modèles SQLAlchemy et le schéma migré ne divergent pas (équivalent d'alembic check)."""
    with moteur.connect() as connexion:
        differences = compare_metadata(MigrationContext.configure(connexion), Base.metadata)
    assert differences == []


def test_meme_numero_de_texte_dans_deux_legislatures(donnees_minimales: Connection) -> None:
    connexion = donnees_minimales
    connexion.execute(insert(Legislature).values(numero=16, debut="2022-06-28", fin="2024-06-09"))
    connexion.execute(insert(Dossier).values(id="DLR_TEST_16", legislature=16, titre_officiel="Autre", type="proposition"))
    connexion.execute(insert(Texte).values(legislature=16, numero="3851", dossier_id="DLR_TEST_16", type="depose"))
    connexion.execute(insert(Texte).values(legislature=17, numero="3851", dossier_id="DLR_TEST_1", type="depose"))

    with pytest.raises(IntegrityError):
        connexion.execute(insert(Texte).values(legislature=17, numero="3851", dossier_id="DLR_TEST_1", type="adopte"))


def test_valeur_hors_liste_refusee(donnees_minimales: Connection) -> None:
    with pytest.raises(IntegrityError, match="ck_dossier_statut"):
        donnees_minimales.execute(update(Dossier).values(statut="enterre"))


def test_maj_le_avance_a_chaque_mise_a_jour(donnees_minimales: Connection) -> None:
    connexion = donnees_minimales
    # Le trigger s'applique aussi à cette mise à jour : on remet donc une date ancienne
    # en désactivant les triggers, le temps de la préparer.
    connexion.execute(text("ALTER TABLE dossier DISABLE TRIGGER dossier_maj_le"))
    connexion.execute(update(Dossier).values(cree_le="2020-01-01", maj_le="2020-01-01"))
    connexion.execute(text("ALTER TABLE dossier ENABLE TRIGGER dossier_maj_le"))

    connexion.execute(update(Dossier).values(titre_court="Protection des forêts"))

    cree_le, maj_le = connexion.execute(select(Dossier.cree_le, Dossier.maj_le)).one()
    assert cree_le.year == 2020
    assert maj_le.year > 2020


def test_recherche_intervention_ignore_accents_et_pluriels(donnees_minimales: Connection) -> None:
    connexion = donnees_minimales
    connexion.execute(
        insert(Intervention).values(
            seance_id="RUANR_TEST_1",
            ordre=1,
            orateur_libelle="Mme Exemple",
            qualite="depute",
            texte="Les députés ont adopté l'amendement relatif aux forêts.",
        )
    )

    def trouve(recherche: str) -> bool:
        requete = select(Intervention.id).where(
            Intervention.recherche.op("@@")(text(f"plainto_tsquery('francais', '{recherche}')"))
        )
        return connexion.execute(requete).first() is not None

    assert trouve("deputes")  # sans accent
    assert trouve("amendements adoptés")  # pluriel et forme conjuguée
    assert trouve("foret")
    assert not trouve("budget")


def test_recherche_dossier_par_alias(donnees_minimales: Connection) -> None:
    requete = select(Dossier.id).where(
        Dossier.recherche.op("@@")(text("plainto_tsquery('francais', 'martin')"))
    )
    assert donnees_minimales.execute(requete).scalar_one() == "DLR_TEST_1"


def test_quatre_arguments_maximum(connexion: Connection) -> None:
    """Charte de neutralité : 4 arguments au plus par groupe."""
    with pytest.raises(IntegrityError, match="ck_argument_ordre"):
        connexion.execute(insert(Argument).values(position_id=1, ordre=5, texte="…"))
