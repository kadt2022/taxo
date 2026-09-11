"""Initial projects and scan snapshots."""
from alembic import op
import sqlalchemy as sa

revision = '001'
down_revision = None


def upgrade():
    op.create_table('projects', sa.Column('id', sa.String(), primary_key=True), sa.Column('name', sa.String(), nullable=False), sa.Column('path', sa.String(), nullable=False, unique=True))
    op.create_table('scans', sa.Column('id', sa.String(), primary_key=True), sa.Column('project_id', sa.String(), sa.ForeignKey('projects.id'), nullable=False), sa.Column('created_at', sa.DateTime(timezone=True), nullable=False), sa.Column('result', sa.JSON(), nullable=False))
    op.create_index('ix_scans_project_id', 'scans', ['project_id'])


def downgrade():
    op.drop_table('scans')
    op.drop_table('projects')
