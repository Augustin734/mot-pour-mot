"""Routes des lois (dossiers législatifs) : liste, recherche et fiche.

Une « loi » de l'interface est un dossier législatif de l'AN (identifiant DLR…).
"""

from datetime import date, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from pydantic import BaseModel
from sqlalchemy import ColumnElement, func, literal, select
from sqlalchemy.orm import Session

from api import recherche
from api.base import session
from api.pagination import Page, Pagination, pagination, paginer
from db.modeles import STATUTS_DOSSIER, TYPES_DOSSIER, Dossier, Etape, Scrutin

routeur = APIRouter(prefix="/lois", tags=["Lois"])

# Sans recherche, les lois sont triées par dernière activité. Les dates absentes sont
# remplacées par une date antérieure à tout dossier (début de la Ve République) : la clé
# de tri n'est jamais NULL, ce qu'exige la comparaison de tuples de la pagination.
DATE_PLANCHER = datetime.fromisoformat("1958-10-04T00:00:00+00:00")


class Loi(BaseModel):
    id: str
    titre: str  # titre court s'il existe, sinon titre officiel
    titre_officiel: str
    type: Literal[TYPES_DOSSIER]
    statut: Literal[STATUTS_DOSSIER]
    date_depot: date | None
    date_derniere_activite: datetime | None
    themes: list[str]


class LoiTrouvee(Loi):
    # Titre affiché, HTML échappé, mots cherchés entourés de <mark> ; vide sans recherche.
    titre_surligne: str | None


class EtapeLoi(BaseModel):
    type: str
    chambre: str | None
    date: date | None


class ScrutinLoi(BaseModel):
    id: str
    numero: int | None
    date: date | None
    objet: str
    type: str
    resultat: str
    pour: int
    contre: int
    abstentions: int


class FicheLoi(Loi):
    titre_court: str | None
    alias: list[str]
    etape_courante: EtapeLoi | None  # dernière étape déjà datée
    etapes: list[EtapeLoi]  # ordre chronologique, étapes sans date à la fin
    scrutins: list[ScrutinLoi]  # du plus récent au plus ancien


def titre_affiche() -> ColumnElement[str]:
    return func.coalesce(Dossier.titre_court, Dossier.titre_officiel)


def en_loi(dossier: Dossier) -> dict:
    return {
        "id": dossier.id,
        "titre": dossier.titre_court or dossier.titre_officiel,
        "titre_officiel": dossier.titre_officiel,
        "type": dossier.type,
        "statut": dossier.statut,
        "date_depot": dossier.date_depot,
        "date_derniere_activite": dossier.date_derniere_activite,
        "themes": dossier.themes,
    }


@routeur.get("", summary="Lois, avec recherche plein texte dans les titres et alias")
def lister_lois(
    db: Annotated[Session, Depends(session)],
    page: Annotated[Pagination, Depends(pagination)],
    q: Annotated[str | None, Query(description="Mots cherchés (\"expression exacte\", -exclu)")] = None,
    statut: Annotated[Literal[STATUTS_DOSSIER] | None, Query()] = None,
    theme: Annotated[str | None, Query()] = None,
) -> Page[LoiTrouvee]:
    requete = select(Dossier)
    if statut is not None:
        requete = requete.where(Dossier.statut == statut)
    if theme is not None:
        requete = requete.where(Dossier.themes.contains([theme]))

    q = q.strip() if q else None
    if q:
        tsquery = recherche.requete(q)
        requete = requete.add_columns(
            recherche.surligner(titre_affiche(), tsquery, "HighlightAll=true")
        ).where(Dossier.recherche.op("@@")(tsquery))
        cles = [recherche.pertinence(Dossier.recherche, tsquery), Dossier.id]
    else:
        requete = requete.add_columns(literal(None))
        cles = [func.coalesce(Dossier.date_derniere_activite, DATE_PLANCHER), Dossier.id]

    lignes, suivant = paginer(db, requete, cles, page)
    return Page(
        resultats=[LoiTrouvee(**en_loi(dossier), titre_surligne=surligne) for dossier, surligne in lignes],
        next_cursor=suivant,
    )


@routeur.get("/{id}", summary="Fiche d'une loi : étapes et scrutins")
def lire_loi(
    db: Annotated[Session, Depends(session)],
    id: Annotated[str, Path(description="Identifiant AN du dossier (DLR…)")],
) -> FicheLoi:
    dossier = db.get(Dossier, id)
    if dossier is None:
        raise HTTPException(404, f"Loi introuvable : {id}")

    etapes = db.scalars(
        select(Etape)
        .where(Etape.dossier_id == id)
        .order_by(Etape.date.asc().nulls_last(), Etape.id)
    ).all()
    scrutins = db.scalars(
        select(Scrutin)
        .where(Scrutin.dossier_id == id)
        .order_by(Scrutin.date.desc().nulls_last(), Scrutin.numero.desc().nulls_last())
    ).all()

    aujourd_hui = date.today()
    passees = [e for e in etapes if e.date is not None and e.date <= aujourd_hui]
    return FicheLoi(
        **en_loi(dossier),
        titre_court=dossier.titre_court,
        alias=dossier.alias,
        etape_courante=EtapeLoi.model_validate(passees[-1], from_attributes=True) if passees else None,
        etapes=[EtapeLoi.model_validate(e, from_attributes=True) for e in etapes],
        scrutins=[ScrutinLoi.model_validate(s, from_attributes=True) for s in scrutins],
    )
