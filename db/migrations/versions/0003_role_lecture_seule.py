"""Crée le rôle lecture_seule : droits de lecture sur le schéma, pour l'API.

Le rôle n'a pas de droit de connexion : l'utilisateur de l'API en est membre, et il est
créé à part (python -m db.utilisateur_api) pour que son mot de passe reste dans .env.
Un rôle existe pour tout le serveur PostgreSQL, alors que les droits sont propres à
chaque base : le rôle est donc créé s'il manque, puis les droits sont donnés ici.

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-01 16:00:00

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '0003'
down_revision: Union[str, Sequence[str], None] = '0002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Crée le rôle et lui donne la lecture des tables actuelles et futures."""
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'lecture_seule') THEN
                CREATE ROLE lecture_seule NOLOGIN;
            END IF;
        END
        $$
        """
    )
    op.execute("GRANT USAGE ON SCHEMA public TO lecture_seule")
    op.execute("GRANT SELECT ON ALL TABLES IN SCHEMA public TO lecture_seule")
    # Les tables créées plus tard par les migrations (même propriétaire) seront lisibles aussi.
    op.execute("ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO lecture_seule")


def downgrade() -> None:
    """Retire les droits dans cette base ; le rôle reste, car d'autres bases peuvent l'utiliser."""
    op.execute("ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE SELECT ON TABLES FROM lecture_seule")
    op.execute("REVOKE SELECT ON ALL TABLES IN SCHEMA public FROM lecture_seule")
    op.execute("REVOKE USAGE ON SCHEMA public FROM lecture_seule")
