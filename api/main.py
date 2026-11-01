"""Point d'entrée de l'API : uvicorn api.main:app

Spécification : docs/cadrage/08-specification-de-l-api.md
"""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from api.base import session
from db.modeles import RunPipeline, Seance

app = FastAPI(
    title="Mot pour mot",
    description="Ce que chaque groupe de l'Assemblée nationale pense d'une loi. API en lecture seule.",
    version="0.1.0",
    docs_url="/api/v1/docs",
    openapi_url="/api/v1/openapi.json",
)

# --- Erreurs au format de la spécification : {"error": {"code": …, "message": …}} ---

CODES_ERREUR = {400: "requete_invalide", 404: "not_found", 422: "parametre_invalide", 500: "erreur_interne"}


def erreur(statut: int, message: str) -> JSONResponse:
    code = CODES_ERREUR.get(statut, "erreur")
    return JSONResponse(status_code=statut, content={"error": {"code": code, "message": message}})


@app.exception_handler(HTTPException)
async def gerer_http(_: Request, exc: HTTPException) -> JSONResponse:
    return erreur(exc.status_code, str(exc.detail))


@app.exception_handler(404)
async def gerer_route_inconnue(_: Request, __: Exception) -> JSONResponse:
    return erreur(404, "Ressource introuvable")


@app.exception_handler(RequestValidationError)
async def gerer_validation(_: Request, exc: RequestValidationError) -> JSONResponse:
    return erreur(422, "; ".join(e["msg"] for e in exc.errors()))


# --- Routes ------------------------------------------------------------------

v1 = APIRouter(prefix="/api/v1")


class DernierRun(BaseModel):
    debut: datetime
    fin: datetime | None
    statut: str
    nb_nouveaux: int | None


class Statut(BaseModel):
    dernier_run: DernierRun | None
    derniere_seance: datetime | None  # début de la séance la plus récente chargée


@v1.get("/statut", summary="Dernier run de nuit et fraîcheur des données")
def lire_statut(db: Annotated[Session, Depends(session)]) -> Statut:
    run = db.scalars(select(RunPipeline).order_by(RunPipeline.debut.desc()).limit(1)).first()
    derniere_seance = db.scalar(select(func.max(Seance.debut)))
    return Statut(
        dernier_run=DernierRun.model_validate(run, from_attributes=True) if run else None,
        derniere_seance=derniere_seance,
    )


app.include_router(v1)
