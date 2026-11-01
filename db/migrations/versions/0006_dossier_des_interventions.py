"""Ajoute intervention.dossier_id, calculé par pipeline.liaison.

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-01 14:49:34.518962

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0006'
down_revision: Union[str, Sequence[str], None] = '0005'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Ajoute la colonne, son index et sa clé étrangère."""
    op.add_column('intervention', sa.Column('dossier_id', sa.Text(), nullable=True))
    op.create_index(op.f('ix_intervention_dossier_id'), 'intervention', ['dossier_id'], unique=False)
    op.create_foreign_key(op.f('fk_intervention_dossier_id_dossier'), 'intervention', 'dossier', ['dossier_id'], ['id'])


def downgrade() -> None:
    """Retire la colonne."""
    op.drop_constraint(op.f('fk_intervention_dossier_id_dossier'), 'intervention', type_='foreignkey')
    op.drop_index(op.f('ix_intervention_dossier_id'), table_name='intervention')
    op.drop_column('intervention', 'dossier_id')
