"""Tests du rôle lecture_seule et de l'utilisateur de l'API : la base refuse toute écriture."""

import uuid
from collections.abc import Iterator

import pytest
from sqlalchemy import Connection, Engine, create_engine, func, insert, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ProgrammingError

from db.modeles import Legislature, Seance
from db.utilisateur_api import creer_utilisateur


def test_lecture_autorisee_ecriture_refusee(connexion: Connection) -> None:
    connexion.execute(text("SET LOCAL ROLE lecture_seule"))
    assert connexion.scalar(select(func.count()).select_from(Seance)) == 0
    with pytest.raises(ProgrammingError, match="permission denied"):
        connexion.execute(insert(Legislature).values(numero=17, debut="2024-07-18"))


def test_tables_creees_plus_tard_lisibles(connexion: Connection) -> None:
    """Les droits par défaut couvrent les tables des futures migrations."""
    connexion.execute(text("CREATE TABLE table_future (id int)"))
    connexion.execute(text("SET LOCAL ROLE lecture_seule"))
    assert connexion.scalar(text("SELECT count(*) FROM table_future")) == 0


@pytest.fixture
def nom_utilisateur(moteur: Engine) -> Iterator[str]:
    """Nom unique, et rôle supprimé à la fin : un rôle vaut pour tout le serveur."""
    nom = f"api_test_{uuid.uuid4().hex[:8]}"
    yield nom
    with moteur.begin() as connexion:
        connexion.execute(text(f'DROP ROLE IF EXISTS "{nom}"'))


def test_utilisateur_api_lit_sans_pouvoir_ecrire(
    moteur: Engine, url_test: str, nom_utilisateur: str
) -> None:
    # Le premier appel crée l'utilisateur, le second change son mot de passe.
    # Des caractères spéciaux vérifient que le mot de passe est bien échappé.
    with moteur.begin() as connexion:
        creer_utilisateur(connexion, nom_utilisateur, "ancien")
        creer_utilisateur(connexion, nom_utilisateur, "nouveau 'mot' de % passe")

    url = make_url(url_test).set(username=nom_utilisateur, password="nouveau 'mot' de % passe")
    moteur_api = create_engine(url)
    try:
        with moteur_api.connect() as connexion:
            assert connexion.scalar(select(func.count()).select_from(Seance)) == 0
            with pytest.raises(ProgrammingError, match="permission denied"):
                connexion.execute(insert(Legislature).values(numero=17, debut="2024-07-18"))
    finally:
        moteur_api.dispose()
