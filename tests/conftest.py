"""Fixtures communes : une base de test dédiée, migrée par Alembic.

Les tests tournent sur le PostgreSQL de docker compose, dans une base séparée
(<nom>_test) recréée à chaque session : la base de travail n'est jamais touchée.
"""

from collections.abc import Iterator

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, Engine, create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError

from db.connexion import url_base


def config_alembic(url: str) -> Config:
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", url)
    return config


@pytest.fixture(scope="session")
def url_test() -> str:
    url = make_url(url_base())
    url_test = url.set(database=f"{url.database}_test")
    # Connexion à la base « postgres » pour pouvoir supprimer et recréer la base de test.
    admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as connexion:
            connexion.execute(text(f'DROP DATABASE IF EXISTS "{url_test.database}" WITH (FORCE)'))
            connexion.execute(text(f'CREATE DATABASE "{url_test.database}"'))
    except OperationalError as erreur:
        pytest.fail(f"Base injoignable, lancer « docker compose up -d » : {erreur}")
    finally:
        admin.dispose()
    rendu = url_test.render_as_string(hide_password=False)
    command.upgrade(config_alembic(rendu), "head")
    return rendu


@pytest.fixture(scope="session")
def moteur(url_test: str) -> Iterator[Engine]:
    moteur = create_engine(url_test)
    yield moteur
    moteur.dispose()


@pytest.fixture
def connexion(moteur: Engine) -> Iterator[Connection]:
    """Connexion dans une transaction annulée à la fin du test : chaque test part d'une base vide."""
    with moteur.connect() as connexion:
        transaction = connexion.begin()
        yield connexion
        transaction.rollback()
