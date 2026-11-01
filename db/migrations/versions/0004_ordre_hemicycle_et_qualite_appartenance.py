"""Ajoute groupe.ordre_hemicycle et appartenance.qualite (membre, apparenté, président…).

La table appartenance est encore vide avant cette migration (rien ne la remplissait) :
la colonne qualite peut donc être créée NOT NULL sans valeur par défaut.

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-01 14:04:51.640808

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0004'
down_revision: Union[str, Sequence[str], None] = '0003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Ajoute les deux colonnes et la liste fermée des qualités."""
    op.add_column('appartenance', sa.Column('qualite', sa.Text(), nullable=False))
    # Alembic ne détecte pas les CHECK : contrainte écrite à la main (voir db.modeles).
    op.create_check_constraint(
        'qualite', 'appartenance', "qualite IN ('membre', 'apparente', 'president', 'non_inscrit')"
    )
    op.add_column('groupe', sa.Column('ordre_hemicycle', sa.Integer(), nullable=True))


def downgrade() -> None:
    """Retire les colonnes (la contrainte part avec sa colonne)."""
    op.drop_column('groupe', 'ordre_hemicycle')
    op.drop_column('appartenance', 'qualite')
