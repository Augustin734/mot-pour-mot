"""Tests de l'API : route /statut, format des erreurs, lecture seule."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Connection, insert
from sqlalchemy.orm import Session

from api.base import session
from api.main import app
from db.modeles import Legislature, RunPipeline, Seance


@pytest.fixture
def client(connexion: Connection) -> Iterator[TestClient]:
    """Client dont les requêtes lisent la transaction du test (annulée à la fin)."""

    def session_de_test() -> Iterator[Session]:
        with Session(bind=connexion, join_transaction_mode="create_savepoint") as s:
            yield s

    app.dependency_overrides[session] = session_de_test
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_statut_base_vide(client: TestClient) -> None:
    reponse = client.get("/api/v1/statut")
    assert reponse.status_code == 200
    assert reponse.json() == {"dernier_run": None, "derniere_seance": None}


def test_statut_renvoie_le_dernier_run(client: TestClient, connexion: Connection) -> None:
    connexion.execute(
        insert(RunPipeline),
        [
            {"debut": "2026-10-30T02:00:00+00:00", "statut": "echec", "nb_nouveaux": None},
            {"debut": "2026-10-31T02:00:00+00:00", "statut": "succes", "nb_nouveaux": 42},
        ],
    )
    connexion.execute(insert(Legislature).values(numero=17, debut="2024-07-18"))
    connexion.execute(insert(Seance).values(id="RUANR_TEST", legislature=17, debut="2026-10-29T15:00:00+00:00"))

    corps = client.get("/api/v1/statut").json()

    assert corps["dernier_run"]["statut"] == "succes"
    assert corps["dernier_run"]["nb_nouveaux"] == 42
    assert corps["derniere_seance"].startswith("2026-10-29T15:00:00")


def test_erreur_au_format_de_la_spec(client: TestClient) -> None:
    reponse = client.get("/api/v1/inconnue")
    assert reponse.status_code == 404
    assert reponse.json() == {"error": {"code": "not_found", "message": "Ressource introuvable"}}


def test_api_en_lecture_seule(client: TestClient) -> None:
    """Aucune route n'accepte autre chose que GET (spécification de l'API)."""
    methodes = {m for route in app.routes for m in getattr(route, "methods", set())}
    assert methodes <= {"GET", "HEAD"}
    assert client.post("/api/v1/statut").status_code == 405
