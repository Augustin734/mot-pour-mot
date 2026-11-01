"""Liaison des interventions : orateur → député et groupe à la date, intervention → dossier.

    uv run python -m pipeline.liaison                  # 17e législature
    uv run python -m pipeline.liaison --legislature 16

À lancer après le chargement des acteurs, des dossiers et des comptes rendus. Tout est
recalculé à chaque passage et seules les valeurs qui changent sont écrites : une
correction de l'open data (nouveau mandat, nouveau texte) se propage au run suivant.

Règles :
- Groupe : seulement pour une intervention de qualité député ou rapporteur. Un ministre
  parle au nom du gouvernement, et un vice-président qui préside la séance au nom de la
  présidence : leur parole n'est pas attribuée à leur groupe (charte de neutralité).
- Dossier d'un point de l'ordre du jour : le dossier le plus cité par les numéros de texte
  de ses interventions ; à défaut, le dossier dont le titre est exactement celui du point,
  une fois retirés les accents, la ponctuation et le préfixe juridique (« Projet de loi
  de… »), et s'il est le seul dans ce cas. Pas de rapprochement approché : « Motion de
  censure » serait sinon relié à « Instaurer une motion de censure constructive ».
- Dossier d'une intervention : celui de son propre texte, sinon celui de son point.
"""

import argparse
import logging
import re
import unicodedata
from dataclasses import dataclass, field

from sqlalchemy import Connection, bindparam, text, update

from db.connexion import creer_moteur
from db.modeles import PointOdj

journal = logging.getLogger("pipeline.liaison")

PREFIXE_JURIDIQUE = re.compile(
    r"^(projet|proposition) de loi( organique| constitutionnelle)?"
    r"( visant a| tendant a| relatif a( la| l| au| aux)?| relative a( la| l| au| aux)?"
    r"| portant| pour| de la| de l| des| du| de| d| sur)? "
)

ORATEURS = text(
    """
    WITH cible AS (
        SELECT i.id, d.id AS depute_id,
               CASE WHEN i.qualite IN ('depute', 'rapporteur') THEN (
                   SELECT a.groupe_id FROM appartenance a
                   WHERE a.depute_id = d.id
                     AND (s.debut AT TIME ZONE 'Europe/Paris')::date
                         BETWEEN a.debut AND coalesce(a.fin, 'infinity'::date)
                   ORDER BY a.debut DESC
                   LIMIT 1
               ) END AS groupe_id
        FROM intervention i
        JOIN seance s ON s.id = i.seance_id
        LEFT JOIN depute d ON d.id = i.acteur_id
        WHERE s.legislature = :legislature
    )
    UPDATE intervention i
    SET depute_id = c.depute_id, groupe_id = c.groupe_id
    FROM cible c
    WHERE c.id = i.id
      AND (i.depute_id IS DISTINCT FROM c.depute_id OR i.groupe_id IS DISTINCT FROM c.groupe_id)
    """
)

# Dossier le plus cité par point ; à égalité, celui cité en premier dans la séance.
DOSSIER_MAJORITAIRE = text(
    """
    SELECT point_id, dossier_id FROM (
        SELECT i.point_id, t.dossier_id,
               row_number() OVER (PARTITION BY i.point_id ORDER BY count(*) DESC, min(i.ordre)) AS rang
        FROM intervention i
        JOIN seance s ON s.id = i.seance_id
        JOIN texte t ON t.legislature = s.legislature AND t.numero = i.numero_texte
        WHERE s.legislature = :legislature AND i.point_id IS NOT NULL
        GROUP BY i.point_id, t.dossier_id
    ) votes
    WHERE rang = 1
    """
)

DOSSIER_DES_INTERVENTIONS = text(
    """
    WITH cible AS (
        SELECT i.id, coalesce(t.dossier_id, p.dossier_id) AS dossier_id
        FROM intervention i
        JOIN seance s ON s.id = i.seance_id
        LEFT JOIN texte t ON t.legislature = s.legislature AND t.numero = i.numero_texte
        LEFT JOIN point_odj p ON p.id = i.point_id
        WHERE s.legislature = :legislature
    )
    UPDATE intervention i
    SET dossier_id = c.dossier_id
    FROM cible c
    WHERE c.id = i.id AND i.dossier_id IS DISTINCT FROM c.dossier_id
    """
)

BILAN = text(
    """
    SELECT count(*) AS interventions,
           count(i.dossier_id) AS avec_dossier,
           count(*) FILTER (WHERE i.qualite IN ('depute', 'rapporteur')) AS parlementaires,
           count(i.groupe_id) AS avec_groupe
    FROM intervention i JOIN seance s ON s.id = i.seance_id
    WHERE s.legislature = :legislature
    """
)

# Numéros cités en séance mais absents de la table texte (résolutions, textes à venir…).
NUMEROS_INCONNUS = text(
    """
    SELECT i.numero_texte, count(*) AS n
    FROM intervention i JOIN seance s ON s.id = i.seance_id
    WHERE s.legislature = :legislature AND i.numero_texte IS NOT NULL AND i.dossier_id IS NULL
    GROUP BY 1 ORDER BY 2 DESC LIMIT 10
    """
)

POINTS_SANS_DOSSIER = text(
    """
    SELECT split_part(p.titre, E'\\n', 1) AS titre, count(*) AS n
    FROM intervention i
    JOIN seance s ON s.id = i.seance_id
    JOIN point_odj p ON p.id = i.point_id
    WHERE s.legislature = :legislature AND i.dossier_id IS NULL
    GROUP BY 1 ORDER BY 2 DESC LIMIT 10
    """
)


@dataclass
class BilanLiaison:
    interventions: int = 0
    avec_dossier: int = 0
    parlementaires: int = 0  # interventions de qualité député ou rapporteur
    avec_groupe: int = 0
    ecritures: dict[str, int] = field(default_factory=dict)
    numeros_inconnus: list[tuple[str, int]] = field(default_factory=list)
    points_sans_dossier: list[tuple[str, int]] = field(default_factory=list)


def normaliser_titre(titre: str) -> str:
    """« Projet de loi de finances pour 2026 » → « finances pour 2026 » (voir le module)."""
    titre = titre.split("\n", 1)[0]
    # Apostrophes en espaces avant de retirer les accents, sinon « l’élection » → « lelection ».
    titre = re.sub(r"[’']", " ", titre)
    titre = unicodedata.normalize("NFKD", titre).encode("ascii", "ignore").decode().lower()
    titre = re.sub(r"\(suite\)", "", titre)
    titre = re.sub(r"[^a-z0-9]+", " ", titre).strip()
    return PREFIXE_JURIDIQUE.sub("", titre)


def index_des_titres(dossiers: list[tuple[str, str]]) -> dict[str, str]:
    """Titre normalisé → dossier, pour les seuls titres portés par un dossier unique."""
    candidats: dict[str, set[str]] = {}
    for identifiant, titre in dossiers:
        candidats.setdefault(normaliser_titre(titre), set()).add(identifiant)
    return {titre: ids.pop() for titre, ids in candidats.items() if len(ids) == 1 and titre}


def lier_points(connexion: Connection, legislature: int) -> int:
    """Renseigne point_odj.dossier_id. Renvoie le nombre de points modifiés."""
    majoritaire = dict(connexion.execute(DOSSIER_MAJORITAIRE, {"legislature": legislature}).all())
    titres = index_des_titres(connexion.execute(text("SELECT id, titre_officiel FROM dossier")).all())
    points = connexion.execute(
        text(
            "SELECT p.id, p.titre, p.dossier_id FROM point_odj p "
            "JOIN seance s ON s.id = p.seance_id WHERE s.legislature = :legislature"
        ),
        {"legislature": legislature},
    ).all()

    changements = []
    for point_id, titre, actuel in points:
        cible = majoritaire.get(point_id) or titres.get(normaliser_titre(titre))
        if cible != actuel:
            changements.append({"b_id": point_id, "b_dossier": cible})
    if changements:
        connexion.execute(
            update(PointOdj)
            .where(PointOdj.id == bindparam("b_id"))
            .values(dossier_id=bindparam("b_dossier")),
            changements,
        )
    return len(changements)


def lier(connexion: Connection, legislature: int) -> BilanLiaison:
    parametres = {"legislature": legislature}
    ecritures = {
        "orateurs": connexion.execute(ORATEURS, parametres).rowcount,
        "points": lier_points(connexion, legislature),
        "dossiers": connexion.execute(DOSSIER_DES_INTERVENTIONS, parametres).rowcount,
    }
    chiffres = connexion.execute(BILAN, parametres).one()
    return BilanLiaison(
        **chiffres._asdict(),
        ecritures=ecritures,
        numeros_inconnus=[tuple(r) for r in connexion.execute(NUMEROS_INCONNUS, parametres)],
        points_sans_dossier=[tuple(r) for r in connexion.execute(POINTS_SANS_DOSSIER, parametres)],
    )


def _pourcentage(partie: int, total: int) -> str:
    return f"{100 * partie / total:.1f} %" if total else "-"


def main(arguments: list[str] | None = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parseur = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parseur.add_argument("--legislature", type=int, default=17)
    args = parseur.parse_args(arguments)

    with creer_moteur().begin() as connexion:
        bilan = lier(connexion, args.legislature)
    journal.info("Lignes modifiées : %s", bilan.ecritures)
    journal.info(
        "%d interventions, %s rattachées à un dossier ; %s des interventions de députés avec un groupe",
        bilan.interventions,
        _pourcentage(bilan.avec_dossier, bilan.interventions),
        _pourcentage(bilan.avec_groupe, bilan.parlementaires),
    )
    journal.info("Numéros de texte inconnus les plus cités : %s", bilan.numeros_inconnus)
    journal.info("Points sans dossier les plus longs : %s", bilan.points_sans_dossier)


if __name__ == "__main__":
    main()
