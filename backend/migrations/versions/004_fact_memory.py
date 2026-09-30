"""Versioned fact memory (TAXO-01E): identities, occurrences, evidence and producer executions.

Creates the new storage and fills it from `analysis_facts`, which is never modified. Each analysis is
migrated and verified in its own transaction: an interruption keeps the analyses already done, and
running the migration again resumes with the next one. The first inconsistency stops the migration
with its reason, before anything of that analysis is written.

The split of a fact is a frozen copy of the v1 rules (as in 003): this file imports nothing from `app`.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql, sqlite

import hashlib
import json
import time
import unicodedata
import rfc8785

revision = '004'
down_revision = '003'

_BATCH = 2000
_IDENTITY_DOMAIN = b'taxo-fact-identity/v1\n'
_FIELDS = {
    'ASSERTION': ('kind', 'subject', 'relation', 'object', 'qualifiers'),
    'ABSENCE': ('kind', 'pattern', 'scope', 'method'),
    'COVERAGE': ('kind', 'subject', 'coverage_type', 'scope'),
}
_EVIDENCE = ('path', 'line_start', 'line_end', 'symbol', 'method', 'content_hash', 'object')
_OCCURRENCE = {'snapshot', 'produced_by', 'evidence', 'status', 'validity'}
_EXECUTABLE = ('EVALUATOR', 'PROJECTION')
_NEW_TABLES = ('analysis_snapshots', 'producer_executions', 'fact_identities', 'fact_occurrences', 'fact_evidence')


class MigrationStopped(RuntimeError):
    """An analysis cannot be migrated without loss; nothing of it was written."""


def _say(message):
    print(f'[migration 004] {message}', flush=True)


def _stop(scan_id, reason):
    raise MigrationStopped(f'Analyse {scan_id} : {reason} Migration arrêtée ; analysis_facts est intacte.')


# ——— Frozen v1 split ———

def _normalize(value):
    if isinstance(value, str):
        return unicodedata.normalize('NFC', value)
    if isinstance(value, list):
        return [_normalize(item) for item in value]
    if isinstance(value, dict):
        return {_normalize(key): _normalize(item) for key, item in value.items()}
    return value


def _canonical(fact):
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
    return json.loads(rfc8785.dumps(identity))


def _spelling(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'))


def _stated(identity):
    return {key: value for key, value in identity.items() if key != 'producer_id'}


def _split(scan_id, fact, snapshot):
    if not isinstance(fact, dict) or fact.get('kind') not in _FIELDS:
        _stop(scan_id, 'nature de fait inconnue.')
    if fact.get('snapshot') != snapshot:
        _stop(scan_id, "un fait n'a pas l'instantané de l'analyse.")
    identity = _canonical(fact)
    raw = {key: fact[key] for key in _FIELDS[fact['kind']] if key in fact}
    evidence = None
    if 'evidence' in fact:
        evidence = []
        for item in fact['evidence']:
            if item.get('repository') != snapshot['repository'] or item.get('commit') != snapshot['commit']:
                _stop(scan_id, "une preuve ne vient pas de l'instantané de l'analyse.")
            if not set(item) <= {'repository', 'commit', *_EVIDENCE}:
                _stop(scan_id, 'une preuve porte un champ que la mémoire ne sait pas conserver.')
            evidence.append({key: value for key, value in item.items() if key not in ('repository', 'commit')})
    parts = {'identity_hash': 'sha256:' + hashlib.sha256(_IDENTITY_DOMAIN + rfc8785.dumps(identity)).hexdigest(),
             'identity': identity,
             'raw_identity': None if _spelling(raw) == _spelling(_stated(identity)) else raw,
             'status': fact.get('status'), 'validity': fact.get('validity'), 'evidence': evidence,
             'details': {key: value for key, value in fact.items() if key not in _OCCURRENCE and key not in raw}}
    if _spelling(_rebuild(parts, snapshot, fact['produced_by'])) != _spelling(fact):
        _stop(scan_id, 'un fait ne peut pas être conservé sans perte.')
    return parts


def _rebuild(parts, snapshot, produced_by):
    fact = {**(parts['raw_identity'] or _stated(parts['identity'])), **parts['details'],
            'status': parts['status'], 'validity': parts['validity'],
            'snapshot': dict(snapshot), 'produced_by': dict(produced_by)}
    if parts['evidence'] is not None:
        fact['evidence'] = [{'repository': snapshot['repository'], 'commit': snapshot['commit'], **item}
                            for item in parts['evidence']]
    return fact


def _reference_hash(reference):
    return hashlib.sha256((reference or '').encode()).hexdigest()


def _order_key(reference, identity, occurrence):
    ordered = unicodedata.normalize('NFC', reference or '').encode('utf-16-be').hex()
    return f'{ordered}!{identity}!{occurrence}'


def _produced_by(execution):
    fields = {'producer_type': execution['producer_type'], 'producer_id': execution['producer_id'],
              'producer_version': execution['producer_version'], 'execution_id': execution['execution_id']}
    if execution['producer_type'] == 'EVALUATOR':
        fields |= {'catalog_id': execution['catalog_id'], 'catalog_version': execution['catalog_version']}
    return fields


# ——— Schema ———

def _create_tables():
    existing = set(sa.inspect(op.get_bind()).get_table_names())
    if 'analysis_snapshots' not in existing:
        op.create_table('analysis_snapshots',
                        sa.Column('scan_id', sa.String(), sa.ForeignKey('scans.id'), primary_key=True),
                        sa.Column('snapshot', sa.JSON(), nullable=False))
    if 'producer_executions' not in existing:
        op.create_table('producer_executions',
                        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
                        sa.Column('scan_id', sa.String(), sa.ForeignKey('scans.id'), nullable=False),
                        sa.Column('execution_id', sa.String(), nullable=False),
                        sa.Column('producer_type', sa.String(), nullable=False),
                        sa.Column('producer_id', sa.String(), nullable=False),
                        sa.Column('producer_version', sa.String(), nullable=False),
                        sa.Column('catalog_id', sa.String()), sa.Column('catalog_version', sa.String()),
                        sa.UniqueConstraint('scan_id', 'execution_id', name='uq_producer_executions_scan_execution'))
    if 'fact_identities' not in existing:
        op.create_table('fact_identities',
                        sa.Column('identity_hash', sa.String(71), primary_key=True),
                        sa.Column('kind', sa.String(), nullable=False),
                        sa.Column('subject', sa.Text()), sa.Column('relation', sa.String()),
                        sa.Column('object', sa.Text()), sa.Column('identity', sa.JSON(), nullable=False))
        op.create_index('ix_fact_identities_subject', 'fact_identities', ['subject'])
        op.create_index('ix_fact_identities_object', 'fact_identities', ['object'])
        op.create_index('ix_fact_identities_relation', 'fact_identities', ['relation', 'kind'])
    if 'fact_occurrences' not in existing:
        op.create_table('fact_occurrences',
                        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
                        sa.Column('scan_id', sa.String(), sa.ForeignKey('scans.id'), nullable=False),
                        sa.Column('identity_hash', sa.String(71), sa.ForeignKey('fact_identities.identity_hash'),
                                  nullable=False),
                        sa.Column('execution', sa.Integer(), sa.ForeignKey('producer_executions.id')),
                        sa.Column('human_producer_id', sa.String()),
                        sa.Column('status', sa.String(), nullable=False),
                        sa.Column('validity', sa.String(), nullable=False),
                        sa.Column('raw_identity', sa.JSON()), sa.Column('details', sa.JSON()),
                        sa.Column('has_evidence', sa.Boolean(), nullable=False),
                        sa.Column('relation', sa.String()), sa.Column('subject_hash', sa.String(64)),
                        sa.Column('object_hash', sa.String(64)), sa.Column('occurrence_hash', sa.String(64)),
                        sa.Column('outgoing_rank', sa.BigInteger()), sa.Column('incoming_rank', sa.BigInteger()))
        op.create_index('ix_fact_occurrences_analysis', 'fact_occurrences', ['scan_id', 'id'])
        op.create_index('ix_fact_occurrences_identity', 'fact_occurrences', ['identity_hash', 'scan_id'])
        op.create_index('ix_fact_occurrences_outgoing', 'fact_occurrences',
                        ['scan_id', 'subject_hash', 'relation', 'outgoing_rank'])
        op.create_index('ix_fact_occurrences_incoming', 'fact_occurrences',
                        ['scan_id', 'object_hash', 'relation', 'incoming_rank'])
    if 'fact_evidence' not in existing:
        op.create_table('fact_evidence',
                        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
                        sa.Column('occurrence', sa.Integer(), sa.ForeignKey('fact_occurrences.id'), nullable=False),
                        sa.Column('position', sa.Integer(), nullable=False),
                        sa.Column('path', sa.Text()), sa.Column('line_start', sa.Integer()),
                        sa.Column('line_end', sa.Integer()), sa.Column('symbol', sa.Text()),
                        sa.Column('method', sa.String()), sa.Column('content_hash', sa.String()),
                        sa.Column('object', sa.String()))
        op.create_index('ix_fact_evidence_occurrence', 'fact_evidence', ['occurrence', 'position'])


# Lightweight tables: the migration never depends on the application's models.
_source = sa.table('analysis_facts', sa.column('id', sa.Integer), sa.column('scan_id', sa.String),
                   sa.column('evaluator_id', sa.String), sa.column('fact', sa.JSON))
_scans = sa.table('scans', sa.column('id', sa.String), sa.column('result', sa.JSON))
_snapshots = sa.table('analysis_snapshots', sa.column('scan_id', sa.String), sa.column('snapshot', sa.JSON))
_executions = sa.table('producer_executions', sa.column('id', sa.Integer), sa.column('scan_id', sa.String),
                       *(sa.column(name, sa.String) for name in ('execution_id', 'producer_type', 'producer_id',
                                                                 'producer_version', 'catalog_id',
                                                                 'catalog_version')))
_identities = sa.table('fact_identities', sa.column('identity_hash', sa.String), sa.column('kind', sa.String),
                       sa.column('subject', sa.Text), sa.column('relation', sa.String), sa.column('object', sa.Text),
                       sa.column('identity', sa.JSON))
_occurrences = sa.table('fact_occurrences', *(sa.column(name, kind) for name, kind in (
    ('id', sa.Integer), ('scan_id', sa.String), ('identity_hash', sa.String), ('execution', sa.Integer),
    ('human_producer_id', sa.String), ('status', sa.String), ('validity', sa.String),
    ('raw_identity', sa.JSON(none_as_null=True)), ('details', sa.JSON(none_as_null=True)),
    ('has_evidence', sa.Boolean), ('relation', sa.String), ('subject_hash', sa.String), ('object_hash', sa.String),
    ('occurrence_hash', sa.String), ('outgoing_rank', sa.BigInteger), ('incoming_rank', sa.BigInteger))))
_evidence = sa.table('fact_evidence', sa.column('occurrence', sa.Integer), sa.column('position', sa.Integer),
                     *(sa.column(name, sa.Integer if name.startswith('line') else sa.String) for name in _EVIDENCE))


# ——— Data ———

def _chunks(connection, scan_id):
    last = 0
    while True:
        rows = connection.execute(sa.select(_source.c.id, _source.c.evaluator_id, _source.c.fact)
                                  .where(_source.c.scan_id == scan_id, _source.c.id > last)
                                  .order_by(_source.c.id).limit(_BATCH)).all()
        if not rows:
            return
        yield rows
        last = rows[-1][0]


def _provenance(connection, scan_id):
    """Snapshot, executions and ranks of one analysis, checked against its summary; never invented.

    Ranks are known before writing (occurrences take consecutive ids in source order), so each row is
    inserted once, with its ranks: no update, hence no dead rows on PostgreSQL.
    """
    snapshot, executions, keys, position = None, {}, [], 0
    for rows in _chunks(connection, scan_id):
        for _, evaluator_id, fact in rows:
            position += 1
            if not isinstance(fact, dict):
                _stop(scan_id, "un fait enregistré n'est pas un objet JSON.")
            if snapshot is None:
                snapshot = fact.get('snapshot')
            if not isinstance(snapshot, dict) or fact.get('snapshot') != snapshot:
                _stop(scan_id, "les faits n'ont pas tous le même instantané.")
            produced = fact.get('produced_by') or {}
            if produced.get('producer_id') != evaluator_id:
                _stop(scan_id, "le producteur d'un fait n'est pas l'évaluateur qui l'a enregistré.")
            if produced.get('producer_type') in _EXECUTABLE:
                if executions.setdefault(produced.get('execution_id'), produced) != produced:
                    _stop(scan_id, 'une même exécution porte deux provenances différentes.')
            elif produced != {'producer_type': 'HUMAN', 'producer_id': evaluator_id}:
                _stop(scan_id, 'producteur inconnu.')
            if fact.get('kind') == 'ASSERTION':
                identity = _canonical(fact)
                keys.append((position, _reference_hash(fact.get('subject')), _reference_hash(fact.get('object')),
                             fact.get('relation'), identity.get('subject'), identity.get('object'),
                             hashlib.sha256(_IDENTITY_DOMAIN + rfc8785.dumps(identity)).hexdigest(),
                             hashlib.sha256(_spelling(fact).encode()).hexdigest()))
    result = connection.scalar(sa.select(_scans.c.result).where(_scans.c.id == scan_id)) or {}
    summaries = {item.get('execution_id'): item for item in result.get('evaluations', [])}
    for item in summaries.values():
        if 'snapshot' in item and item['snapshot'] != snapshot:
            _stop(scan_id, "le résumé de l'analyse n'a pas l'instantané de ses faits.")
    for execution_id, produced in executions.items():
        summary = summaries.get(execution_id)
        if summary is None:
            _stop(scan_id, f"l'exécution {execution_id} n'est pas dans le résumé de l'analyse.")
        if (summary.get('evaluator_id'), summary.get('producer_version')) != (
                produced['producer_id'], produced['producer_version']):
            _stop(scan_id, f"l'exécution {execution_id} ne concorde pas avec le résumé de l'analyse.")
    return snapshot, executions, _rank(keys)


def _insert_identities(connection, rows):
    dialect = postgresql if connection.dialect.name == 'postgresql' else sqlite
    connection.execute(dialect.insert(_identities).on_conflict_do_nothing(index_elements=['identity_hash']), rows)


def _write(connection, scan_id, snapshot, executions, ranks):
    connection.execute(_snapshots.insert(), {'scan_id': scan_id, 'snapshot': snapshot})
    rows = {}
    for execution_id, produced in executions.items():
        connection.execute(_executions.insert(), {
            'scan_id': scan_id, 'execution_id': execution_id, 'producer_type': produced['producer_type'],
            'producer_id': produced['producer_id'], 'producer_version': produced['producer_version'],
            'catalog_id': produced.get('catalog_id'), 'catalog_version': produced.get('catalog_version')})
    for row in connection.execute(sa.select(_executions).where(_executions.c.scan_id == scan_id)).mappings():
        rows[row['execution_id']] = row['id']
    # Explicit ids keep the order of analysis_facts, and bind each evidence to its occurrence.
    next_id = (connection.scalar(sa.select(sa.func.max(_occurrences.c.id))) or 0) + 1
    first = next_id
    for chunk in _chunks(connection, scan_id):
        identities, occurrences, evidence = {}, [], []
        for _, _, fact in chunk:
            parts = _split(scan_id, fact, snapshot)
            produced = fact['produced_by']
            identity = parts['identity']
            identities[parts['identity_hash']] = {
                'identity_hash': parts['identity_hash'], 'kind': identity['kind'], 'subject': identity.get('subject'),
                'relation': identity.get('relation'), 'object': identity.get('object'), 'identity': identity}
            anchors = {'relation': None, 'subject_hash': None, 'object_hash': None, 'occurrence_hash': None}
            if fact['kind'] == 'ASSERTION':
                occurrence = hashlib.sha256(_spelling(fact).encode()).hexdigest()
                anchors = {'relation': fact.get('relation'), 'subject_hash': _reference_hash(fact.get('subject')),
                           'object_hash': _reference_hash(fact.get('object')), 'occurrence_hash': occurrence}
            executable = produced['producer_type'] in _EXECUTABLE
            occurrences.append({
                'id': next_id, 'scan_id': scan_id, 'identity_hash': parts['identity_hash'],
                'execution': rows[produced['execution_id']] if executable else None,
                'human_producer_id': None if executable else produced['producer_id'],
                'status': parts['status'], 'validity': parts['validity'], 'raw_identity': parts['raw_identity'],
                'details': parts['details'] or None, 'has_evidence': parts['evidence'] is not None,
                **ranks.get(next_id - first + 1, {'outgoing_rank': None, 'incoming_rank': None}), **anchors})
            evidence += [{'occurrence': next_id, 'position': position,
                          **{name: item.get(name) for name in _EVIDENCE}}
                         for position, item in enumerate(parts['evidence'] or ())]
            next_id += 1
        _insert_identities(connection, list(identities.values()))
        connection.execute(_occurrences.insert(), occurrences)
        if evidence:
            connection.execute(_evidence.insert(), evidence)
    return first, next_id - first


def _rank(keys):
    """Local ranks, 1..n within each adjacency (anchor, relation, direction), in adjacency_keys order."""
    ranks = {}
    for column, anchor, reference in (('outgoing_rank', 1, 5), ('incoming_rank', 2, 4)):
        groups = {}
        for item in keys:
            groups.setdefault((item[anchor], item[3]), []).append(item)
        for members in groups.values():
            members.sort(key=lambda item: _order_key(item[reference], item[6], item[7]))
            for rank, item in enumerate(members, 1):
                ranks.setdefault(item[0], {})[column] = rank
    return ranks


def _verify(connection, scan_id, snapshot, first, count):
    """Every occurrence rebuilt and compared with its source fact, in order."""
    execution_rows = {row['id']: row for row in connection.execute(
        sa.select(_executions).where(_executions.c.scan_id == scan_id)).mappings()}
    position = first
    for chunk in _chunks(connection, scan_id):
        last = position + len(chunk) - 1
        stored = connection.execute(
            sa.select(_occurrences, _identities.c.identity)
            .join(_identities, _identities.c.identity_hash == _occurrences.c.identity_hash)
            .where(_occurrences.c.id.between(position, last)).order_by(_occurrences.c.id)).mappings().all()
        proofs = {}
        for item in connection.execute(sa.select(_evidence).where(_evidence.c.occurrence.between(position, last))
                                       .order_by(_evidence.c.occurrence, _evidence.c.position)).mappings():
            proofs.setdefault(item['occurrence'], []).append(
                {name: item[name] for name in _EVIDENCE if item[name] is not None})
        if len(stored) != len(chunk) or any(row['scan_id'] != scan_id for row in stored):
            _stop(scan_id, 'le nombre de faits relus ne correspond pas.')
        for (_, _, fact), row in zip(chunk, stored):
            produced = (_produced_by(execution_rows[row['execution']]) if row['execution'] is not None
                        else {'producer_type': 'HUMAN', 'producer_id': row['human_producer_id']})
            parts = {'identity': row['identity'], 'raw_identity': row['raw_identity'], 'status': row['status'],
                     'validity': row['validity'], 'details': row['details'] or {},
                     'evidence': proofs.get(row['id'], []) if row['has_evidence'] else None}
            if _spelling(_rebuild(parts, snapshot, produced)) != _spelling(fact):
                _stop(scan_id, 'un fait relu diffère de son original.')
        position = last + 1
    if position - first != count:
        _stop(scan_id, 'le nombre de faits relus ne correspond pas.')


def _sizes(connection):
    names = ('analysis_facts', *_NEW_TABLES)
    if connection.dialect.name == 'postgresql':
        return {name: connection.scalar(sa.text('SELECT pg_total_relation_size(:name)'), {'name': name})
                for name in names}
    try:
        rows = connection.execute(sa.text('SELECT name, tbl_name FROM sqlite_master WHERE type IN (\'table\', \'index\')')).all()
        owner = {name: table for name, table in rows}
        sizes = dict.fromkeys(names, 0)
        for name, size in connection.execute(sa.text('SELECT name, SUM(pgsize) FROM dbstat GROUP BY name')).all():
            if owner.get(name) in sizes:
                sizes[owner[name]] += size
        return sizes
    except sa.exc.DBAPIError:
        return None


def _report(engine, migrated, occurrences, seconds):
    with engine.connect() as connection:
        identities = connection.scalar(sa.select(sa.func.count()).select_from(_identities))
        total = connection.scalar(sa.select(sa.func.count()).select_from(_occurrences))
        proofs = connection.scalar(sa.select(sa.func.count()).select_from(_evidence))
        sizes = _sizes(connection)
    _say(f'Mesure : {migrated} analyses migrées ici, {occurrences} occurrences écrites en {seconds:.0f} s.')
    _say(f'Mesure : {total} occurrences, {identities} identités distinctes, {proofs} preuves.')
    if identities:
        _say(f'Mesure : ratio occurrences / identités = {total / identities:.2f}.')
    if sizes is None:
        _say('Mesure : tailles non disponibles (dbstat absent de ce SQLite).')
        return
    old, new = sizes['analysis_facts'], sum(sizes[name] for name in _NEW_TABLES)
    _say(f'Mesure : analysis_facts (table et index) {old / 1e6:.1f} Mo telle quelle, conservée jusqu\'à 005.')
    _say(f'Mesure : nouveau stockage (tables et index) {new / 1e6:.1f} Mo : '
         + ', '.join(f'{name} {sizes[name] / 1e6:.1f} Mo' for name in _NEW_TABLES) + '.')


def _fill(engine):
    with engine.connect() as connection:
        scans = connection.scalars(sa.select(_source.c.scan_id).distinct().order_by(_source.c.scan_id)).all()
    _say(f'{len(scans)} analyses à reprendre dans la mémoire versionnée ; analysis_facts reste intacte.')
    started, migrated, written = time.monotonic(), 0, 0
    for number, scan_id in enumerate(scans, 1):
        with engine.begin() as connection:
            if connection.scalar(sa.select(_snapshots.c.scan_id).where(_snapshots.c.scan_id == scan_id)):
                _say(f'  analyse {number}/{len(scans)} : déjà migrée (reprise).')
                continue
            begun = time.monotonic()
            snapshot, executions, ranks = _provenance(connection, scan_id)
            first, count = _write(connection, scan_id, snapshot, executions, ranks)
            _verify(connection, scan_id, snapshot, first, count)
        migrated, written = migrated + 1, written + count
        _say(f'  analyse {number}/{len(scans)} : {count} faits migrés et vérifiés en {time.monotonic() - begun:.1f} s.')
    if engine.dialect.name == 'postgresql':
        with engine.begin() as connection:
            for table in ('fact_occurrences', 'fact_evidence', 'producer_executions'):
                connection.execute(sa.text(f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), "
                                           f"(SELECT COALESCE(MAX(id), 0) + 1 FROM {table}), false)"))
        # Give the planner the statistics of the tables just filled.
        with engine.begin() as connection:
            for table in _NEW_TABLES:
                connection.execute(sa.text(f'ANALYZE {table}'))
    _report(engine, migrated, written, time.monotonic() - started)


def upgrade():
    _create_tables()
    # Commit the schema, then one transaction per analysis: an interruption keeps what is done.
    with op.get_context().autocommit_block():
        _fill(op.get_bind().engine)


def downgrade():
    for table in reversed(_NEW_TABLES):
        op.drop_table(table)
