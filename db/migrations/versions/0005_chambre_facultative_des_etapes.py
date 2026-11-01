"""Rend etape.chambre facultative : la CMP et la promulgation ne relèvent d'aucune chambre.

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-01 15:30:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0005'
down_revision: Union[str, Sequence[str], None] = '0004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Autorise une chambre vide."""
    op.alter_column('etape', 'chambre', existing_type=sa.Text(), nullable=True)


def downgrade() -> None:
    """Exige de nouveau une chambre (échoue si des étapes sans chambre existent)."""
    op.alter_column('etape', 'chambre', existing_type=sa.Text(), nullable=False)
