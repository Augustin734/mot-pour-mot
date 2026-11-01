"""Chargement idempotent des séances lues en base (voir pipeline.ecriture).

Une intervention a pour clé (seance_id, ordre) ; les autres lignes, leur identifiant AN.
"""

from dataclasses import dataclass

from sqlalchemy import Connection

from db.modeles import Intervention, PointOdj, Seance
from pipeline.ecriture import upsert
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


def charger_seance(connexion: Connection, seance: SeanceLue) -> Bilan:
    assurer_legislature(connexion, seance.legislature)
    upsert(
        connexion,
        Seance.__table__,
        [{"id": seance.id, "legislature": seance.legislature, "debut": seance.debut}],
        ["id"],
    )
    upsert(
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
    ecrites = upsert(connexion, Intervention.__table__, lignes, ["seance_id", "ordre"])
    return Bilan(seances=1, interventions_ecrites=ecrites)
