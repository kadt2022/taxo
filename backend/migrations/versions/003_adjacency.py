"""Indexed incoming/outgoing adjacency, backfilled without reanalysing repositories."""
from alembic import op
import sqlalchemy as sa

from app.scans.domain.fact_order import adjacency_keys

revision = '003'
down_revision = '002'


def upgrade():
    op.add_column('analysis_facts', sa.Column('outgoing_key', sa.Text()))
    op.add_column('analysis_facts', sa.Column('incoming_key', sa.Text()))
    table = sa.table('analysis_facts', sa.column('id', sa.Integer), sa.column('fact', sa.JSON),
                     sa.column('outgoing_key', sa.Text), sa.column('incoming_key', sa.Text))
    connection = op.get_bind()
    last = 0
    while True:
        rows = connection.execute(sa.select(table.c.id, table.c.fact).where(table.c.id > last)
                                  .order_by(table.c.id).limit(500)).all()
        if not rows:
            break
        for identifier, fact in rows:
            outgoing, incoming = adjacency_keys(fact)
            connection.execute(table.update().where(table.c.id == identifier)
                               .values(outgoing_key=outgoing, incoming_key=incoming))
        last = rows[-1][0]
    for side, anchor in (('outgoing', 'subject'), ('incoming', 'object')):
        op.create_index(f'ix_analysis_facts_{side}', 'analysis_facts',
                        ['scan_id', 'kind', anchor, 'relation', f'{side}_key'])


def downgrade():
    for side in ('incoming', 'outgoing'):
        op.drop_index(f'ix_analysis_facts_{side}', 'analysis_facts')
        op.drop_column('analysis_facts', f'{side}_key')
