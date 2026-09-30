"""Indexed incoming/outgoing adjacency, backfilled without reanalysing repositories."""
from alembic import op
import sqlalchemy as sa

import hashlib
import json
import unicodedata
import rfc8785

# Frozen v1 canonical identity for already validated persisted occurrences.
_FIELDS = {
    'ASSERTION': ('kind', 'subject', 'relation', 'object', 'qualifiers'),
    'ABSENCE': ('kind', 'pattern', 'scope', 'method'),
    'COVERAGE': ('kind', 'subject', 'coverage_type', 'scope'),
}


def _normalize(value):
    if isinstance(value, str):
        return unicodedata.normalize('NFC', value)
    if isinstance(value, list):
        return [_normalize(item) for item in value]
    if isinstance(value, dict):
        return {_normalize(key): _normalize(item) for key, item in value.items()}
    return value


def _keys(fact):
    identity = {key: fact[key] for key in _FIELDS[fact['kind']] if key in fact}
    if fact['kind'] == 'COVERAGE':
        identity['producer_id'] = fact['produced_by']['producer_id']
    identity = _normalize(identity)
    if 'scope' in identity:
        scope = identity['scope']
        for key in ('include', 'exclude'):
            if key in scope:
                scope[key] = sorted(set(scope[key]), key=lambda item: item.encode('utf-16-be'))
        if not scope.get('exclude'):
            scope.pop('exclude', None)
    digest = hashlib.sha256(b'taxo-fact-identity/v1\n' + rfc8785.dumps(identity)).hexdigest()
    occurrence = hashlib.sha256(json.dumps(fact, sort_keys=True, ensure_ascii=False,
                                          separators=(',', ':')).encode()).hexdigest()
    def key(reference):
        ordered = unicodedata.normalize('NFC', reference or '').encode('utf-16-be').hex()
        return f'{ordered}!{digest}!{occurrence}'
    return key(fact.get('object')), key(fact.get('subject'))


def _hash(reference):
    return hashlib.sha256((reference or '').encode()).hexdigest()


revision = '003'
down_revision = '002'


def upgrade():
    columns = [sa.Column('outgoing_key', sa.Text()), sa.Column('incoming_key', sa.Text()),
               sa.Column('subject_hash', sa.String(64)), sa.Column('object_hash', sa.String(64)),
               sa.Column('outgoing_rank', sa.BigInteger()), sa.Column('incoming_rank', sa.BigInteger())]
    for col in columns:
        op.add_column('analysis_facts', col)
    table = sa.table('analysis_facts', sa.column('id', sa.Integer), sa.column('scan_id', sa.String),
                     sa.column('fact', sa.JSON), *(sa.column(col.name, col.type) for col in columns))
    connection = op.get_bind()
    last = 0
    while True:
        rows = connection.execute(sa.select(table.c.id, table.c.fact).where(table.c.id > last)
                                  .order_by(table.c.id).limit(500)).all()
        if not rows:
            break
        for identifier, fact in rows:
            outgoing, incoming = _keys(fact)
            connection.execute(table.update().where(table.c.id == identifier)
                               .values(outgoing_key=outgoing, incoming_key=incoming,
                                       subject_hash=_hash(fact.get('subject')),
                                       object_hash=_hash(fact.get('object'))))
        last = rows[-1][0]
    for scan_id in connection.scalars(sa.select(table.c.scan_id).distinct()).all():
        rows = connection.execute(sa.select(table.c.id, table.c.outgoing_key, table.c.incoming_key)
                                  .where(table.c.scan_id == scan_id)).all()
        for position, side in ((1, 'outgoing'), (2, 'incoming')):
            values = [{'_id': row.id, '_rank': rank} for rank, row in
                      enumerate(sorted(rows, key=lambda item: item[position]), 1)]
            if values:
                connection.execute(table.update().where(table.c.id == sa.bindparam('_id'))
                                   .values({f'{side}_rank': sa.bindparam('_rank')}), values)
    op.create_index('ix_analysis_facts_revision', 'analysis_facts', ['scan_id', 'id'])
    for side, anchor in (('outgoing', 'subject'), ('incoming', 'object')):
        op.create_index(f'ix_analysis_facts_{side}', 'analysis_facts',
                        ['scan_id', 'kind', f'{anchor}_hash', 'relation', f'{side}_rank'])


def downgrade():
    op.drop_index('ix_analysis_facts_revision', 'analysis_facts')
    for side, anchor in (('incoming', 'object'), ('outgoing', 'subject')):
        op.drop_index(f'ix_analysis_facts_{side}', 'analysis_facts')
        for name in (f'{side}_key', f'{side}_rank', f'{anchor}_hash'):
            op.drop_column('analysis_facts', name)
