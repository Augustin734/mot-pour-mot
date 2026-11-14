"""Pagination par curseur : limit (20 par défaut, 100 au plus) et cursor, réponse avec next_cursor.

Pagination « keyset » plutôt qu'OFFSET : le curseur contient les valeurs de tri du dernier
élément renvoyé, et la page suivante reprend strictement après lui. Le coût d'une page ne
grandit pas avec son rang, et une ligne ajoutée par le run de nuit ne décale pas les pages
déjà vues. Le curseur est opaque pour le client (JSON encodé en base64url).

Toutes les clés de tri sont décroissantes et la dernière est un identifiant unique : la
comparaison de tuples (a, b) < (x, y) de PostgreSQL suffit alors à reprendre la liste.
"""

import base64
import binascii
import json
from collections.abc import Sequence
from datetime import datetime
from typing import Annotated, Any

from fastapi import HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import ColumnElement, Row, Select, tuple_
from sqlalchemy.orm import Session

LIMITE_DEFAUT = 20
LIMITE_MAX = 100


class Pagination(BaseModel):
    limit: int = LIMITE_DEFAUT
    cursor: str | None = None


def pagination(
    limit: Annotated[int, Query(ge=1, le=LIMITE_MAX, description="Nombre de résultats par page")] = LIMITE_DEFAUT,
    cursor: Annotated[str | None, Query(description="Curseur renvoyé par la page précédente")] = None,
) -> Pagination:
    # Un curseur vide (cursor=) vaut une première page.
    return Pagination(limit=limit, cursor=cursor or None)


class Page[T](BaseModel):
    resultats: list[T]
    next_cursor: str | None


def encoder_curseur(valeurs: Sequence[Any]) -> str:
    serialisables = [v.isoformat() if isinstance(v, datetime) else v for v in valeurs]
    return base64.urlsafe_b64encode(json.dumps(serialisables).encode()).decode()


def decoder_curseur(curseur: str, cles: Sequence[ColumnElement]) -> list[Any]:
    """Valeurs du curseur, reconverties d'après le type des clés de tri."""
    try:
        valeurs = json.loads(base64.urlsafe_b64decode(curseur.encode()))
        if not isinstance(valeurs, list) or len(valeurs) != len(cles):
            raise ValueError
        return [
            datetime.fromisoformat(v) if cle.type.python_type is datetime else v
            for v, cle in zip(valeurs, cles, strict=True)
        ]
    except (binascii.Error, UnicodeDecodeError, ValueError, TypeError):
        raise HTTPException(400, "Curseur invalide") from None


def paginer(
    db: Session, requete: Select, cles: Sequence[ColumnElement], page: Pagination
) -> tuple[list[Row], str | None]:
    """Exécute une page de la requête triée par les clés (décroissantes).

    Les lignes renvoyées gardent les colonnes de la requête, sans les clés de tri.
    """
    if page.cursor is not None:
        requete = requete.where(tuple_(*cles) < tuple_(*decoder_curseur(page.cursor, cles)))
    # Une entité ORM compte pour une seule colonne de résultat (column_descriptions).
    nb_colonnes = len(requete.column_descriptions)
    requete = (
        requete.add_columns(*cles).order_by(*(cle.desc() for cle in cles)).limit(page.limit + 1)
    )
    lignes = db.execute(requete).all()
    # Une ligne de plus que demandé indique qu'il existe une page suivante.
    suivant = encoder_curseur(lignes[page.limit - 1][nb_colonnes:]) if len(lignes) > page.limit else None
    return [ligne[:nb_colonnes] for ligne in lignes[: page.limit]], suivant
