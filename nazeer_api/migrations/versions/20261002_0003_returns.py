"""returns (P5)

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-02 16:00:00
"""
from alembic import op
import sqlalchemy as sa

revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('returns',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('org_id', sa.String(length=32), nullable=False),
    sa.Column('share_id', sa.String(length=32), nullable=False),
    sa.Column('twin_id', sa.String(length=32), nullable=False),
    sa.Column('submitted_by', sa.String(length=32), nullable=True),
    sa.Column('file_name', sa.String(length=200), nullable=False),
    sa.Column('rows_total', sa.Integer(), nullable=False),
    sa.Column('rows_accepted', sa.Integer(), nullable=False),
    sa.Column('rejected', sa.JSON(), nullable=False),
    sa.Column('columns', sa.JSON(), nullable=False),
    sa.Column('blob_id', sa.String(length=32), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('relink_status', sa.String(length=16), nullable=False),
    sa.Column('relink_error', sa.String(length=64), nullable=True),
    sa.Column('relink_by', sa.String(length=32), nullable=True),
    sa.Column('relink_upload_id', sa.String(length=32), nullable=True),
    sa.Column('relinked_blob_id', sa.String(length=32), nullable=True),
    sa.Column('relink_expires_at', sa.DateTime(), nullable=True),
    sa.Column('relink_matched', sa.Integer(), nullable=True),
    sa.Column('relink_downloads', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['blob_id'], ['blobs.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['relink_by'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['relink_upload_id'], ['blobs.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['relinked_blob_id'], ['blobs.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['share_id'], ['shares.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['submitted_by'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['twin_id'], ['twins.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('returns', schema=None) as batch_op:
        batch_op.create_index('ix_returns_org_created', ['org_id', 'created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_returns_share_id'), ['share_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_returns_twin_id'), ['twin_id'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('returns', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_returns_twin_id'))
        batch_op.drop_index(batch_op.f('ix_returns_share_id'))
        batch_op.drop_index('ix_returns_org_created')
    op.drop_table('returns')
