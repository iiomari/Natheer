"""return verification report (P5 token)

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-03 10:00:00
"""
from alembic import op
import sqlalchemy as sa

revision = '0004'
down_revision = '0003'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('returns', schema=None) as batch_op:
        batch_op.add_column(sa.Column('report', sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('returns', schema=None) as batch_op:
        batch_op.drop_column('report')
