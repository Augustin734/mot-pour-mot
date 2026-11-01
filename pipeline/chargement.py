"""Chargement idempotent des séances lues en base.

Chaque ligne est insérée ou mise à jour selon sa clé (identifiant AN, ou (seance_id, ordre)
pour une intervention). La mise à jour n'a lieu que si une valeur a réellement changé :
recharger un compte rendu identique ne touche à rien, et maj_le n'avance que sur une vraie
correction de l'open data. Rien n'est supprimé.
"""

from dataclasses import dataclass

from sqlalchemy import Connection, Table, or_
from sqlalchemy.dialects.postgresql import insert

from db.modeles import Intervention, PointOdj, Seance
from pipeline.referentiel import assurer_legislature
from pipeline.syceron import SeanceLue


@dataclass
class Bilan:
    seances: int = 0
    interventions_ecrites: int = 0  # insérées ou réellement modifiées

    def __iadd__(self, autre: "Bilan") -> "Bilan":
        self.seances += autre.seances
        self.interventions_ecrites += autre.interventions_ecrites
        return self


def _upsert(connexion: Connection, table: Table, lignes: list[dict], cles: list[str]) -> int:
    """INSERT … ON CONFLICT DO UPDATE, seulement si une colonne diffère. Renvoie le nombre
    de lignes insérées ou modifiées."""
    if not lignes:
        return 0
    requete = insert(table).values(lignes)
    colonnes = [c for c in lignes[0] if c not in cles]
    requete = requete.on_conflict_do_update(
        index_elements=cles,
        set_={c: requete.excluded[c] for c in colonnes},
        where=or_(*(table.c[c].is_distinct_from(requete.excluded[c]) for c in colonnes)),
    )
    # RETURNING plutôt que rowcount, qui n'est pas fiable pour un INSERT multi-lignes.
    return len(connexion.execute(requete.returning(table.c[cles[0]])).all())


def charger_seance(connexion: Connection, seance: SeanceLue) -> Bilan:
    assurer_legislature(connexion, seance.legislature)
    _upsert(
        connexion,
        Seance.__table__,
        [{"id": seance.id, "legislature": seance.legislature, "debut": seance.debut}],
        ["id"],
    )
    _upsert(
        connexion,
        PointOdj.__table__,
        [
            {"id": p.id, "seance_id": seance.id, "numero": p.numero, "titre": p.titre}
            for p in seance.points
        ],
        ["id"],
    )
    lignes = [
        {
            "seance_id": seance.id,
            "ordre": i.ordre,
            "point_id": i.point_id,
            "type_debat": i.type_debat,
            "code_grammaire": i.code_grammaire,
            "numero_texte": i.numero_texte,
            "article": i.article,
            "amendement": i.amendement,
            "acteur_id": i.acteur_id,
            "orateur_libelle": i.orateur_libelle,
            "qualite": i.qualite,
            "texte": i.texte,
            "nb_mots": i.nb_mots,
        }
        for i in seance.interventions
    ]
    ecrites = 0
    # Par paquets : PostgreSQL limite le nombre de paramètres d'une requête.
    for debut in range(0, len(lignes), 1000):
        ecrites += _upsert(
            connexion, Intervention.__table__, lignes[debut : debut + 1000], ["seance_id", "ordre"]
        )
    return Bilan(seances=1, interventions_ecrites=ecrites)
