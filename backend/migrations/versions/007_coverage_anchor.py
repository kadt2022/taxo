"""The anchor of each coverage's subject (TAXO-01J): what is unread about a node is read by that node.

Coverage occurrences were written without anchor. Their subject fingerprint is computed again, batch by
batch, from the identity row (sha256 of the reference as recorded). Relation and ranks stay empty: a coverage
is never traversed. Downgrade empties the column again for coverage only.
"""
import hashlib

import sqlalchemy as sa
from alembic import op

revision = '007'
down_revision = '006'

_BATCH = 5000
_occurrences = sa.table('fact_occurrences', sa.column('id', sa.Integer), sa.column('identity_hash', sa.String),
                        sa.column('relation', sa.String), sa.column('subject_hash', sa.String))
_identities = sa.table('fact_identities', sa.column('identity_hash', sa.String), sa.column('kind', sa.String),
                       sa.column('subject', sa.Text))


def _say(message):
    print(f'[migration 007] {message}', flush=True)


def _fingerprint(reference):
    return hashlib.sha256((reference or '').encode()).hexdigest()


def upgrade():
    connection, last, done = op.get_bind(), 0, 0
    while True:
        rows = connection.execute(
            sa.select(_occurrences.c.id, _identities.c.subject)
            .join(_identities, _identities.c.identity_hash == _occurrences.c.identity_hash)
            .where(_identities.c.kind == 'COVERAGE', _occurrences.c.id > last)
            .order_by(_occurrences.c.id).limit(_BATCH)).all()
        if not rows:
            break
        connection.execute(_occurrences.update().where(_occurrences.c.id == sa.bindparam('_id'))
                           .values(subject_hash=sa.bindparam('_hash')),
                           [{'_id': identifier, '_hash': _fingerprint(subject)} for identifier, subject in rows])
        last, done = rows[-1][0], done + len(rows)
    _say(f'{done} couvertures ancrées par leur sujet.')


def downgrade():
    coverage = sa.select(_identities.c.identity_hash).where(_identities.c.kind == 'COVERAGE')
    op.get_bind().execute(_occurrences.update().where(_occurrences.c.identity_hash.in_(coverage))
                          .values(subject_hash=None))
