"""Accès à la base : l'adresse vient de la variable DATABASE_URL (fichier .env)."""

import os

from dotenv import load_dotenv
from sqlalchemy import Engine, create_engine


def url_base() -> str:
    load_dotenv()
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL n'est pas définie : copier .env.example en .env")
    return url


def creer_moteur(url: str | None = None) -> Engine:
    return create_engine(url or url_base())
