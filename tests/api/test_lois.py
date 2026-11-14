"""Tests des routes /lois : liste, recherche plein texte, pagination et fiche.

Les données sont fictives (charte de neutralité : aucun propos réel inventé).
"""

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Connection, insert

from db.modeles import Dossier, Etape, Legislature, Scrutin


def dossier(id: str, titre: str, activite: str | None, **autres: object) -> dict:
    return {
        "id": id,
        "legislature": 17,
        "titre_officiel": titre,
        "type": "proposition",
        "date_derniere_activite": activite,
        "alias": [],
        "titre_court": None,
        "statut": "en_cours",
        "themes": [],
    } | autres


@pytest.fixture
def lois(connexion: Connection) -> Connection:
    connexion.execute(insert(Legislature).values(numero=17, debut="2024-07-18"))
    connexion.execute(
        insert(Dossier),
        [
            dossier("DLR_A", "Projet de loi relatif à la protection des forêts", "2026-10-01T10:00:00+00:00",
                    type="projet", alias=["loi Martin"], themes=["environnement"]),
            dossier("DLR_B", "Proposition de loi visant à rénover les écoles", "2026-10-03T10:00:00+00:00",
                    titre_court="Rénovation des écoles", statut="adopte"),
            dossier("DLR_C", "Proposition de loi sur la forêt communale", "2026-09-15T10:00:00+00:00"),
            dossier("DLR_D", "Proposition de loi <b>balisée</b> & cie", None),
        ],
    )
    return connexion


def ids(reponse) -> list[str]:
    return [loi["id"] for loi in reponse.json()["resultats"]]


def test_liste_par_derniere_activite(client: TestClient, lois: Connection) -> None:
    reponse = client.get("/api/v1/lois")
    assert reponse.status_code == 200
    # Les lois sans date d'activité arrivent en dernier.
    assert ids(reponse) == ["DLR_B", "DLR_A", "DLR_C", "DLR_D"]
    assert reponse.json()["next_cursor"] is None
    premiere = reponse.json()["resultats"][0]
    assert premiere["titre"] == "Rénovation des écoles"  # titre court préféré au titre officiel
    assert premiere["titre_surligne"] is None


def test_recherche_avec_stemming_et_alias(client: TestClient, lois: Connection) -> None:
    # « forêts » retrouve « forêt » et « forêts » ; les accents sont ignorés.
    assert set(ids(client.get("/api/v1/lois", params={"q": "foret"}))) == {"DLR_A", "DLR_C"}
    assert ids(client.get("/api/v1/lois", params={"q": "Martin"})) == ["DLR_A"]
    assert ids(client.get("/api/v1/lois", params={"q": "forêt -communale"})) == ["DLR_A"]


def test_recherche_surligne_et_echappe_le_html(client: TestClient, lois: Connection) -> None:
    resultat = client.get("/api/v1/lois", params={"q": "forêt communale"}).json()["resultats"][0]
    assert resultat["titre_surligne"] == "Proposition de loi sur la <mark>forêt</mark> <mark>communale</mark>"

    resultat = client.get("/api/v1/lois", params={"q": "balisée"}).json()["resultats"][0]
    assert resultat["titre_surligne"] == "Proposition de loi &lt;b&gt;<mark>balisée</mark>&lt;/b&gt; &amp; cie"


def test_filtres(client: TestClient, lois: Connection) -> None:
    assert ids(client.get("/api/v1/lois", params={"statut": "adopte"})) == ["DLR_B"]
    assert ids(client.get("/api/v1/lois", params={"theme": "environnement"})) == ["DLR_A"]
    reponse = client.get("/api/v1/lois", params={"statut": "inconnu"})
    assert reponse.status_code == 422
    assert reponse.json()["error"]["code"] == "parametre_invalide"


def lire_toutes_les_pages(client: TestClient, **params: object) -> list[str]:
    vus, curseur = [], None
    while True:
        corps = client.get("/api/v1/lois", params={**params, "limit": 2, "cursor": curseur}).json()
        vus += [loi["id"] for loi in corps["resultats"]]
        curseur = corps["next_cursor"]
        if curseur is None:
            return vus


def test_pagination_complete_sans_doublon(client: TestClient, lois: Connection) -> None:
    assert lire_toutes_les_pages(client) == ["DLR_B", "DLR_A", "DLR_C", "DLR_D"]


def test_pagination_de_la_recherche_avec_ex_aequo(client: TestClient, connexion: Connection) -> None:
    """Des titres identiques ont la même pertinence : l'identifiant départage les ex aequo."""
    connexion.execute(insert(Legislature).values(numero=17, debut="2024-07-18"))
    connexion.execute(
        insert(Dossier),
        [dossier(f"DLR_{i}", "Proposition de loi sur le logement", None) for i in range(7)]
        + [dossier("DLR_X", "Logement : proposition de loi sur le logement", None)],
    )
    vus = lire_toutes_les_pages(client, q="logement")
    assert vus[0] == "DLR_X"  # deux occurrences : plus pertinent
    assert len(vus) == len(set(vus)) == 8


def test_curseur_invalide(client: TestClient, lois: Connection) -> None:
    reponse = client.get("/api/v1/lois", params={"cursor": "pas-un-curseur"})
    assert reponse.status_code == 400
    assert reponse.json() == {"error": {"code": "requete_invalide", "message": "Curseur invalide"}}


def test_limite_maximale(client: TestClient, lois: Connection) -> None:
    assert client.get("/api/v1/lois", params={"limit": 101}).status_code == 422


def test_fiche_loi(client: TestClient, lois: Connection) -> None:
    demain = date.today() + timedelta(days=1)
    lois.execute(
        insert(Etape),
        [
            {"id": "E3", "dossier_id": "DLR_A", "type": "seance", "chambre": "an", "date": demain},
            {"id": "E1", "dossier_id": "DLR_A", "type": "depot", "chambre": "an", "date": "2026-09-01"},
            {"id": "E2", "dossier_id": "DLR_A", "type": "commission", "chambre": "an", "date": "2026-09-20"},
            {"id": "E4", "dossier_id": "DLR_A", "type": "cmp", "chambre": None, "date": None},
        ],
    )
    scrutin = {"dossier_id": "DLR_A", "type": "ordinaire", "resultat": "adopte", "contre": 10,
               "abstentions": 2, "non_votants": 0}
    lois.execute(
        insert(Scrutin),
        [
            scrutin | {"id": "VT1", "numero": 1, "date": "2026-09-25", "objet": "Amendement n° 1", "pour": 40},
            scrutin | {"id": "VT2", "numero": 2, "date": "2026-09-26", "objet": "Ensemble du texte", "pour": 300},
        ],
    )

    fiche = client.get("/api/v1/lois/DLR_A").json()

    assert fiche["titre"] == fiche["titre_officiel"] == "Projet de loi relatif à la protection des forêts"
    assert fiche["alias"] == ["loi Martin"]
    assert [e["type"] for e in fiche["etapes"]] == ["depot", "commission", "seance", "cmp"]
    # L'étape courante est la dernière déjà passée, pas la séance prévue demain.
    assert fiche["etape_courante"] == {"type": "commission", "chambre": "an", "date": "2026-09-20"}
    assert [s["id"] for s in fiche["scrutins"]] == ["VT2", "VT1"]
    assert fiche["scrutins"][0]["pour"] == 300


def test_fiche_loi_sans_etape(client: TestClient, lois: Connection) -> None:
    fiche = client.get("/api/v1/lois/DLR_C").json()
    assert fiche["etapes"] == [] and fiche["etape_courante"] is None and fiche["scrutins"] == []


def test_loi_introuvable(client: TestClient, lois: Connection) -> None:
    reponse = client.get("/api/v1/lois/DLR_INCONNU")
    assert reponse.status_code == 404
    assert reponse.json() == {"error": {"code": "not_found", "message": "Loi introuvable : DLR_INCONNU"}}
