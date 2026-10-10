"""The references of each analysis, found by their name (TAXO-01N, PR A2, `find_references` with `match: NAME`).

A projection of `analysis_references`: one row per name under which a reference is found (a key ending taken at
the start of a segment). New analyses write it with their facts; this migration fills it for the existing ones,
analysis by analysis, from `analysis_references`, which keeps every reference as submitted. Its rules are frozen
here, copied from the application at the time of writing (a test checks that they still agree): a migration never
imports the application, which may change after it.
"""
import unicodedata

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql, sqlite

revision = '010'
down_revision = '009'

KEY_LENGTH = 256
SEPARATORS = frozenset('./#:$')
_TABLE = 'analysis_reference_names'
_INDEX = 'ix_analysis_reference_names_type'
_references = sa.table('analysis_references', sa.column('scan_id', sa.String), sa.column('reference_hash', sa.String),
                       sa.column('type', sa.String), sa.column('reference', sa.Text))


def _ordered(length):
    return sa.String(length).with_variant(postgresql.VARCHAR(length, collation='C'), 'postgresql')


def _say(message):
    print(f'[migration 010] {message}', flush=True)


def _canonical(text):
    return ''.join('.' if character in SEPARATORS else character for character in text.casefold())


def _callable(kind, key):
    member = key.rfind('#')
    if kind != 'symbol' or member < 0 or not key.endswith(')'):
        return None
    opening = key.find('(', member)
    if opening < 0 or any(character in SEPARATORS for character in key[member + 1:opening]):
        return None
    return key[:opening], key[opening:]


def _endings(text):
    starts = [0, *(position + 1 for position, character in enumerate(text) if character in SEPARATORS)]
    return [text[start:] for start in starts if start < len(text)]


def name_keys(reference):
    kind, _, key = reference.partition(':')
    key = unicodedata.normalize('NFC', key)
    split = _callable(kind, key)
    if split is None:
        found = {_canonical(ending) for ending in _endings(key)}
    else:
        head, parameters = split
        found = {_canonical(ending + listed) for ending in _endings(head) for listed in ('', parameters)}
    return sorted(name for name in found if len(name) <= KEY_LENGTH)


def _columns():
    return [sa.Column('scan_id', sa.String, sa.ForeignKey('scans.id'), primary_key=True),
            sa.Column('name_key', _ordered(KEY_LENGTH), primary_key=True),
            sa.Column('reference_hash', _ordered(64), primary_key=True),
            sa.Column('type', sa.String, nullable=False)]


def _create():
    """Table et index, s'ils manquent : une migration interrompue puis reprise ne recrée rien."""
    inspector = sa.inspect(op.get_bind())
    if _TABLE in inspector.get_table_names():
        _say(f'Table {_TABLE} déjà présente (reprise).')
        table = sa.Table(_TABLE, sa.MetaData(), *_columns())
        present = {index['name'] for index in inspector.get_indexes(_TABLE)}
    else:
        table = op.create_table(_TABLE, *_columns())
        present = set()
    if _INDEX not in present:
        op.create_index(_INDEX, _TABLE, ['scan_id', 'type', 'name_key', 'reference_hash'])
    return table


def upgrade():
    table = _create()
    connection = op.get_bind()
    dialect = postgresql if connection.dialect.name == 'postgresql' else sqlite
    insert = dialect.insert(table).on_conflict_do_nothing(index_elements=['scan_id', 'name_key', 'reference_hash'])
    analyses = connection.scalars(sa.select(_references.c.scan_id).distinct().order_by(_references.c.scan_id)).all()
    total = 0
    for scan_id in analyses:
        values = [{'scan_id': scan_id, 'name_key': name, 'reference_hash': reference_hash, 'type': kind}
                  for reference_hash, kind, reference in connection.execute(
                      sa.select(_references.c.reference_hash, _references.c.type, _references.c.reference)
                      .where(_references.c.scan_id == scan_id))
                  for name in name_keys(reference)]
        for start in range(0, len(values), 500):
            connection.execute(insert, values[start:start + 500])
        total += len(values)
    _say(f'{total} noms indexés pour {len(analyses)} analyses.')


def downgrade():
    op.drop_index(_INDEX, table_name=_TABLE)
    op.drop_table(_TABLE)
