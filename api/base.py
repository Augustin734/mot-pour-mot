"""Session de base de données injectée dans les routes."""

from collections.abc import Iterator
from functools import cache

from sqlalchemy import Engine
from sqlalchemy.orm import Session

from db.connexion import creer_moteur


@cache
def moteur() -> Engine:
    return creer_moteur()


def session() -> Iterator[Session]:
    with Session(moteur()) as session:
        yield session
