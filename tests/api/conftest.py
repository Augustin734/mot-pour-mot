"""Fixtures des tests de l'API."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Connection
from sqlalchemy.orm import Session

from api.base import session
from api.main import app


@pytest.fixture
def client(connexion: Connection) -> Iterator[TestClient]:
    """Client dont les requêtes lisent la transaction du test (annulée à la fin)."""

    def session_de_test() -> Iterator[Session]:
        with Session(bind=connexion, join_transaction_mode="create_savepoint") as s:
            yield s

    app.dependency_overrides[session] = session_de_test
    yield TestClient(app)
    app.dependency_overrides.clear()
