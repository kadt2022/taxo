"""The span and role of a call site in its evidence (TAXO-01K): a proof can point at a call within its lines.

Three nullable columns on `fact_evidence`. Existing evidence has no span and no role, so nothing is filled. SQLite
commits each ALTER TABLE on its own: an interrupted upgrade resumes with the columns still missing instead of
failing. Downgrade drops them again.
"""
import sqlalchemy as sa
from alembic import op

revision = '009'
down_revision = '008'

_TABLE = 'fact_evidence'
_COLUMNS = (('column_start', sa.Integer), ('column_end', sa.Integer), ('role', sa.String))


def upgrade():
    existing = {column['name'] for column in sa.inspect(op.get_bind()).get_columns(_TABLE)}
    for name, kind in _COLUMNS:
        if name not in existing:
            op.add_column(_TABLE, sa.Column(name, kind, nullable=True))


def downgrade():
    with op.batch_alter_table(_TABLE) as table:
        for name, _ in reversed(_COLUMNS):
            table.drop_column(name)
