"""Tests du téléchargement : cache conditionnel, nouvelles tentatives, fichiers tronqués.

Un petit serveur HTTP local remplace le site de l'AN : les tests ne dépendent pas du réseau.
"""

import io
import threading
import urllib.error
import zipfile
from email.utils import parsedate_to_datetime
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from pipeline import telechargement
from pipeline.telechargement import telecharger_url


def archive_zip(contenu: str) -> bytes:
    tampon = io.BytesIO()
    with zipfile.ZipFile(tampon, "w") as archive:
        archive.writestr("donnees.json", contenu)
    return tampon.getvalue()


MATIN = "Sun, 01 Nov 2026 05:25:51 GMT"
MIDI = "Sun, 01 Nov 2026 11:26:06 GMT"


class ServeurDeTest(ThreadingHTTPServer):
    """Sert self.fichiers ({chemin: octets}) et note les requêtes reçues."""

    def __init__(self) -> None:
        super().__init__(("127.0.0.1", 0), Gestionnaire)
        self.fichiers: dict[str, bytes] = {}
        self.etag = '"v1"'
        self.last_modified: str | None = MATIN
        self.erreurs_a_renvoyer: list[int] = []  # codes renvoyés avant de servir le fichier
        self.coupures_a_faire = 0  # réponses tronquées avant de servir le fichier
        self.requetes: list[dict[str, str]] = []

    def url(self, chemin: str) -> str:
        return f"http://127.0.0.1:{self.server_port}{chemin}"


class Gestionnaire(BaseHTTPRequestHandler):
    server: ServeurDeTest

    def do_GET(self) -> None:
        serveur = self.server
        serveur.requetes.append(dict(self.headers))
        if serveur.erreurs_a_renvoyer:
            self.send_error(serveur.erreurs_a_renvoyer.pop(0))
            return
        if self.path not in serveur.fichiers:
            self.send_error(404)
            return
        depuis = self.headers.get("If-Modified-Since")
        a_jour = (
            depuis is not None
            and serveur.last_modified is not None
            and parsedate_to_datetime(serveur.last_modified) <= parsedate_to_datetime(depuis)
        )
        if a_jour or self.headers.get("If-None-Match") == serveur.etag:
            self.send_response(304)
            self.end_headers()
            return
        contenu = serveur.fichiers[self.path]
        self.send_response(200)
        self.send_header("Content-Length", str(len(contenu)))
        self.send_header("ETag", serveur.etag)
        if serveur.last_modified:
            self.send_header("Last-Modified", serveur.last_modified)
        self.end_headers()
        if serveur.coupures_a_faire:
            serveur.coupures_a_faire -= 1
            self.wfile.write(contenu[: len(contenu) // 2])
            self.close_connection = True
            return
        self.wfile.write(contenu)

    def log_message(self, *_: object) -> None:
        pass


@pytest.fixture
def serveur(monkeypatch: pytest.MonkeyPatch) -> Iterator[ServeurDeTest]:
    monkeypatch.setattr(telechargement, "PAUSE_SECONDES", 0)
    serveur = ServeurDeTest()
    fil = threading.Thread(target=serveur.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
    fil.start()
    yield serveur
    serveur.shutdown()
    serveur.server_close()


def test_premier_telechargement_puis_cache(serveur: ServeurDeTest, tmp_path: Path) -> None:
    serveur.fichiers["/a.zip"] = archive_zip("{}")
    destination = tmp_path / "a.zip"

    premier = telecharger_url(serveur.url("/a.zip"), destination)
    second = telecharger_url(serveur.url("/a.zip"), destination)

    assert premier.modifie and not second.modifie
    assert destination.read_bytes() == serveur.fichiers["/a.zip"]
    assert "If-Modified-Since" not in serveur.requetes[0]
    # La date seule : un ETag ferait retélécharger la copie d'un autre serveur de l'AN.
    assert serveur.requetes[1]["If-Modified-Since"] == MATIN
    assert "If-None-Match" not in serveur.requetes[1]


def test_etag_si_pas_de_date(serveur: ServeurDeTest, tmp_path: Path) -> None:
    serveur.fichiers["/a.zip"] = archive_zip("{}")
    serveur.last_modified = None
    destination = tmp_path / "a.zip"
    telecharger_url(serveur.url("/a.zip"), destination)

    assert not telecharger_url(serveur.url("/a.zip"), destination).modifie
    assert serveur.requetes[1]["If-None-Match"] == '"v1"'


def test_copie_plus_ancienne_d_un_autre_serveur_ignoree(serveur: ServeurDeTest, tmp_path: Path) -> None:
    """Cas réel : deux serveurs de l'AN, même contenu, dates et ETag différents."""
    serveur.fichiers["/a.zip"] = archive_zip("{}")
    serveur.last_modified = MIDI
    destination = tmp_path / "a.zip"
    telecharger_url(serveur.url("/a.zip"), destination)

    serveur.last_modified, serveur.etag = MATIN, '"autre-serveur"'
    assert not telecharger_url(serveur.url("/a.zip"), destination).modifie
    assert serveur.requetes[1]["If-Modified-Since"] == MIDI


def test_contenu_identique_avec_une_date_plus_recente(serveur: ServeurDeTest, tmp_path: Path) -> None:
    serveur.fichiers["/a.zip"] = archive_zip("{}")
    destination = tmp_path / "a.zip"
    telecharger_url(serveur.url("/a.zip"), destination)

    serveur.last_modified = MIDI
    assert not telecharger_url(serveur.url("/a.zip"), destination).modifie
    # La nouvelle date est retenue : la requête suivante obtient un 304.
    assert not telecharger_url(serveur.url("/a.zip"), destination).modifie
    assert serveur.requetes[2]["If-Modified-Since"] == MIDI


def test_nouvelle_version_remplace_le_cache(serveur: ServeurDeTest, tmp_path: Path) -> None:
    serveur.fichiers["/a.zip"] = archive_zip("ancien")
    destination = tmp_path / "a.zip"
    telecharger_url(serveur.url("/a.zip"), destination)

    serveur.fichiers["/a.zip"] = archive_zip("nouveau")
    serveur.etag, serveur.last_modified = '"v2"', MIDI
    resultat = telecharger_url(serveur.url("/a.zip"), destination)

    assert resultat.modifie
    assert destination.read_bytes() == serveur.fichiers["/a.zip"]


def test_erreur_serveur_passagere_retentee(serveur: ServeurDeTest, tmp_path: Path) -> None:
    serveur.fichiers["/a.zip"] = archive_zip("{}")
    serveur.erreurs_a_renvoyer = [503]

    assert telecharger_url(serveur.url("/a.zip"), tmp_path / "a.zip").modifie
    assert len(serveur.requetes) == 2


def test_fichier_tronque_retente_sans_ecraser_le_cache(serveur: ServeurDeTest, tmp_path: Path) -> None:
    serveur.fichiers["/a.zip"] = archive_zip("ancien")
    destination = tmp_path / "a.zip"
    telecharger_url(serveur.url("/a.zip"), destination)

    serveur.fichiers["/a.zip"] = archive_zip("nouveau" * 1000)
    serveur.etag, serveur.last_modified = '"v2"', MIDI
    serveur.coupures_a_faire = telechargement.TENTATIVES
    with pytest.raises(OSError, match="incomplet"):
        telecharger_url(serveur.url("/a.zip"), destination)

    # Après trois coupures, l'ancienne archive valide est toujours là.
    assert len(serveur.requetes) == 1 + telechargement.TENTATIVES
    assert zipfile.ZipFile(destination).read("donnees.json") == b"ancien"


def test_url_inexistante_sans_nouvelle_tentative(serveur: ServeurDeTest, tmp_path: Path) -> None:
    with pytest.raises(urllib.error.HTTPError, match="404"):
        telecharger_url(serveur.url("/absent.zip"), tmp_path / "absent.zip")
    assert len(serveur.requetes) == 1


def test_fichier_qui_n_est_pas_un_zip_refuse(serveur: ServeurDeTest, tmp_path: Path) -> None:
    serveur.fichiers["/a.zip"] = b"<html>maintenance</html>"
    with pytest.raises(OSError, match="pas une archive zip"):
        telecharger_url(serveur.url("/a.zip"), tmp_path / "a.zip")
    assert not (tmp_path / "a.zip").exists()


def test_url_des_archives() -> None:
    assert telechargement.url_archive("scrutins", 17) == (
        "https://data.assemblee-nationale.fr/static/openData/repository/17/loi/scrutins/Scrutins.json.zip"
    )
