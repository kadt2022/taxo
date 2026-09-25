"""Faits d'une analyse globale, interrogeables apres l'analyse (TAXO-EVAL-02)."""
from alembic import op
import sqlalchemy as sa

revision = '002'
down_revision = '001'


def upgrade():
    op.create_table('analysis_facts',
                    sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
                    sa.Column('scan_id', sa.String(), sa.ForeignKey('scans.id'), nullable=False),
                    sa.Column('evaluator_id', sa.String(), nullable=False),
                    sa.Column('kind', sa.String(), nullable=False),
                    sa.Column('subject', sa.String()), sa.Column('relation', sa.String()),
                    sa.Column('object', sa.String()), sa.Column('fact', sa.JSON(), nullable=False))
    op.create_index('ix_analysis_facts_scan_id', 'analysis_facts', ['scan_id'])


def downgrade():
    op.drop_index('ix_analysis_facts_scan_id', 'analysis_facts')
    op.drop_table('analysis_facts')
