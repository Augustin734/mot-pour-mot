"""Crée (ou met à jour) l'utilisateur PostgreSQL de l'API, membre du rôle lecture_seule.

    uv run python -m db.utilisateur_api

À lancer après « alembic upgrade head », avec l'utilisateur principal (DATABASE_URL).
Le nom et le mot de passe viennent de API_POSTGRES_USER et API_POSTGRES_PASSWORD (.env) :
ils ne sont jamais écrits dans une migration versionnée. Relancer le script après un
changement de mot de passe le met à jour.
"""

import os

from dotenv import load_dotenv
from psycopg import sql
from sqlalchemy import Connection, text

from db.connexion import creer_moteur

ROLE_LECTURE = "lecture_seule"
UTILISATEUR_PAR_DEFAUT = "motpourmot_api"


def creer_utilisateur(connexion: Connection, nom: str, mot_de_passe: str) -> None:
    existe = connexion.scalar(text("SELECT 1 FROM pg_roles WHERE rolname = :nom"), {"nom": nom})
    # CREATE ROLE n'accepte pas de paramètres liés : le nom et le mot de passe sont
    # échappés par psycopg (Identifier, Literal), jamais concaténés à la main.
    requete = sql.SQL("{} ROLE {} LOGIN PASSWORD {}").format(
        sql.SQL("ALTER" if existe else "CREATE"), sql.Identifier(nom), sql.Literal(mot_de_passe)
    )
    with connexion.connection.driver_connection.cursor() as curseur:
        curseur.execute(requete)
        curseur.execute(
            sql.SQL("GRANT {} TO {}").format(sql.Identifier(ROLE_LECTURE), sql.Identifier(nom))
        )


def main() -> None:
    load_dotenv()
    nom = os.environ.get("API_POSTGRES_USER", UTILISATEUR_PAR_DEFAUT)
    mot_de_passe = os.environ.get("API_POSTGRES_PASSWORD")
    if not mot_de_passe:
        raise SystemExit("API_POSTGRES_PASSWORD n'est pas définie : voir .env.example")
    with creer_moteur().begin() as connexion:
        creer_utilisateur(connexion, nom, mot_de_passe)
    print(f"Utilisateur « {nom} » prêt, en lecture seule.")


if __name__ == "__main__":
    main()
