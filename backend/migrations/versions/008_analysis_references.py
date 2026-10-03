"""The references of each analysis, searchable by prefix (TAXO-01J, `find_references`).

A projection of the versioned memory: one row per reference named by an assertion of the analysis (its
subject, and its object when it is a reference), as it was submitted: the spelling a traversal accepts. New analyses write it with their facts; this migration
fills it for the existing ones, analysis by analysis, from the identity rows. Its rules are frozen here,
copied from the application at the time of writing (a test checks that they still agree): a migration never
imports the application, which may change after it.
"""
import hashlib
import re
import unicodedata

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql, sqlite

revision = '008'
down_revision = '007'

KEY_LENGTH = 256
_REFERENCE = re.compile(r'(repository|module|directory|file|symbol|endpoint|route-pattern|technology|language|'
                        r'annotation|role|permission|policy-rule|commit|person|application):[^\s][^\n\r  ]*')
_occurrences = sa.table('fact_occurrences', sa.column('scan_id', sa.String), sa.column('identity_hash', sa.String),
                        sa.column('raw_identity', sa.JSON))
_identities = sa.table('fact_identities', sa.column('identity_hash', sa.String), sa.column('kind', sa.String),
                       sa.column('subject', sa.Text), sa.column('object', sa.Text))


def _ordered(length):
    return sa.String(length).with_variant(postgresql.VARCHAR(length, collation='C'), 'postgresql')


def _say(message):
    print(f'[migration 008] {message}', flush=True)


def is_reference(value):
    return isinstance(value, str) and _REFERENCE.fullmatch(value) is not None


def row(scan_id, reference):
    kind, _, key = reference.partition(':')
    return {'scan_id': scan_id, 'reference_hash': hashlib.sha256(reference.encode()).hexdigest(),
            'search_key': unicodedata.normalize('NFC', key).casefold()[:KEY_LENGTH], 'type': kind,
            'reference': reference}


_INDEXES = {'ix_analysis_references_key': ['scan_id', 'search_key', 'reference_hash'],
            'ix_analysis_references_type': ['scan_id', 'type', 'search_key', 'reference_hash']}
_COLUMNS = (lambda: [sa.Column('scan_id', sa.String, sa.ForeignKey('scans.id'), primary_key=True),
                     sa.Column('reference_hash', _ordered(64), primary_key=True),
                     sa.Column('search_key', _ordered(KEY_LENGTH), nullable=False),
                     sa.Column('type', sa.String, nullable=False),
                     sa.Column('reference', sa.Text, nullable=False)])


def _create():
    """Table et index, s'ils manquent : une migration interrompue puis reprise ne recrée rien."""
    inspector = sa.inspect(op.get_bind())
    if 'analysis_references' in inspector.get_table_names():
        _say('Table analysis_references déjà présente (reprise).')
        table = sa.Table('analysis_references', sa.MetaData(), *_COLUMNS())
        present = {index['name'] for index in inspector.get_indexes('analysis_references')}
    else:
        table = op.create_table('analysis_references', *_COLUMNS())
        present = set()
    for name, columns in _INDEXES.items():
        if name not in present:
            op.create_index(name, 'analysis_references', columns)
    return table


def upgrade():
    table = _create()
    connection = op.get_bind()
    dialect = postgresql if connection.dialect.name == 'postgresql' else sqlite
    insert = dialect.insert(table).on_conflict_do_nothing(index_elements=['scan_id', 'reference_hash'])
    analyses = connection.scalars(sa.select(_occurrences.c.scan_id).distinct().order_by(_occurrences.c.scan_id)).all()
    total = 0
    for scan_id in analyses:
        named = connection.execute(
            sa.select(_identities.c.subject, _identities.c.object, _occurrences.c.raw_identity)
            .join(_occurrences, _occurrences.c.identity_hash == _identities.c.identity_hash)
            .where(_occurrences.c.scan_id == scan_id, _identities.c.kind == 'ASSERTION')).all()
        rows = {}
        for subject, target, raw in named:
            # L'orthographe soumise, celle que le parcours accepte comme ancre ; sinon la forme canonique.
            spelled = raw or {}
            for reference in (spelled.get('subject', subject), spelled.get('object', target)):
                if is_reference(reference):
                    rows[reference] = row(scan_id, reference)
        values = list(rows.values())
        for start in range(0, len(values), 500):
            connection.execute(insert, values[start:start + 500])
        total += len(values)
    _say(f'{total} références indexées pour {len(analyses)} analyses.')


def downgrade():
    for name in _INDEXES:
        op.drop_index(name, table_name='analysis_references')
    op.drop_table('analysis_references')
