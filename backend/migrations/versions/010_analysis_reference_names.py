"""The references of each analysis, found by their name (TAXO-01N, PR A2, `find_references` with `match: NAME`).

A projection of `analysis_references`: one row per name under which a reference is found (a key ending taken at
the start of a segment). New analyses write it with their facts; this migration fills it for the existing ones,
analysis by analysis, from `analysis_references`, which keeps every reference as submitted. Its rules are frozen
here, copied from the application at the time of writing (a test checks that they still agree): a migration never
imports the application, which may change after it.
"""
import time
import unicodedata

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql, sqlite

revision = '010'
down_revision = '009'

KEY_LENGTH = 256
# Références lues puis noms écrits par lot : la mémoire reste bornée, même pour une très grosse analyse.
_BATCH = 2000
_INSERT_CHUNK = 500
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


def _create_table():
    """La table, si elle manque : une migration interrompue puis reprise ne recrée rien."""
    inspector = sa.inspect(op.get_bind())
    if _TABLE in inspector.get_table_names():
        _say(f'Table {_TABLE} déjà présente (reprise).')
        return sa.Table(_TABLE, sa.MetaData(), *_columns())
    return op.create_table(_TABLE, *_columns())


def _create_index():
    """L'index de recherche, après le remplissage : bâti une fois plutôt que tenu à jour ligne à ligne."""
    if _INDEX in {index['name'] for index in sa.inspect(op.get_bind()).get_indexes(_TABLE)}:
        return
    _say('Création de l\'index de recherche par nom...')
    begun = time.monotonic()
    op.create_index(_INDEX, _TABLE, ['scan_id', 'type', 'name_key', 'reference_hash'])
    _say(f'Index créé en {time.monotonic() - begun:.1f} s.')


def _pages(connection, scan_id):
    """Les références d'une analyse, par pages bornées dans l'ordre de la clé primaire."""
    after = ''
    while True:
        page = connection.execute(
            sa.select(_references.c.reference_hash, _references.c.type, _references.c.reference)
            .where(_references.c.scan_id == scan_id, _references.c.reference_hash > after)
            .order_by(_references.c.reference_hash).limit(_BATCH)).all()
        if not page:
            return
        yield page
        after = page[-1].reference_hash


def _index_analysis(connection, insert, scan_id, number, count):
    """Une analyse entière dans la transaction de l'appelant ; renvoie (références, noms)."""
    references = names = 0
    for page in _pages(connection, scan_id):
        values = [{'scan_id': scan_id, 'name_key': name, 'reference_hash': reference_hash, 'type': kind}
                  for reference_hash, kind, reference in page for name in name_keys(reference)]
        for start in range(0, len(values), _INSERT_CHUNK):
            connection.execute(insert, values[start:start + _INSERT_CHUNK])
        references, names = references + len(page), names + len(values)
        if references % (_BATCH * 50) == 0:
            _say(f'  analyse {number}/{count} : {references} références lues...')
    return references, names


def _fill(engine, table):
    dialect = postgresql if engine.dialect.name == 'postgresql' else sqlite
    insert = dialect.insert(table).on_conflict_do_nothing(index_elements=['scan_id', 'name_key', 'reference_hash'])
    with engine.connect() as connection:
        analyses = connection.scalars(sa.select(_references.c.scan_id).distinct().order_by(_references.c.scan_id)).all()
    _say(f'{len(analyses)} analyses à indexer par nom ; analysis_references reste intacte.')
    total = 0
    for number, scan_id in enumerate(analyses, 1):
        begun = time.monotonic()
        with engine.begin() as connection:
            # Une analyse s'écrit dans une seule transaction : une ligne présente veut dire analyse complète.
            if connection.scalar(sa.select(table.c.scan_id).where(table.c.scan_id == scan_id).limit(1)):
                _say(f'  analyse {number}/{len(analyses)} : déjà indexée (reprise).')
                continue
            references, names = _index_analysis(connection, insert, scan_id, number, len(analyses))
        total += names
        _say(f'  analyse {number}/{len(analyses)} : {names} noms pour {references} références '
             f'en {time.monotonic() - begun:.1f} s.')
    _say(f'{total} noms indexés pour {len(analyses)} analyses.')


def upgrade():
    table = _create_table()
    # Valider la table, puis une transaction par analyse : une interruption garde ce qui est fait.
    with op.get_context().autocommit_block():
        _fill(op.get_bind().engine, table)
        _create_index()


def downgrade():
    op.drop_index(_INDEX, table_name=_TABLE)
    op.drop_table(_TABLE)
