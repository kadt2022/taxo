"""State of each existing analysis's memory (TAXO-01F): complete, or interrupted during consolidation.

An analysis is complete when the versioned memory holds exactly the facts its summary announces
(facts and coverage of every evaluator) and its snapshot is recorded. Otherwise its consolidation was
interrupted: it stays in the database, marked INCOMPLETE, and is no longer offered as an analysis.
Analyses without an evaluation summary predate the fact store and are left as they are.
"""
from alembic import op
import sqlalchemy as sa

revision = '006'
down_revision = '005'

_scans = sa.table('scans', sa.column('id', sa.String), sa.column('result', sa.JSON))
_snapshots = sa.table('analysis_snapshots', sa.column('scan_id', sa.String))
_occurrences = sa.table('fact_occurrences', sa.column('scan_id', sa.String))


def _say(message):
    print(f'[migration 006] {message}', flush=True)


def upgrade():
    connection = op.get_bind()
    stored = dict(connection.execute(sa.select(_occurrences.c.scan_id, sa.func.count())
                                     .group_by(_occurrences.c.scan_id)).all())
    recorded = set(connection.scalars(sa.select(_snapshots.c.scan_id)))
    complete, incomplete = 0, []
    for scan_id, result in connection.execute(sa.select(_scans.c.id, _scans.c.result)).all():
        if 'memory' in result or 'evaluations' not in result:
            continue
        announced = sum(item.get('fact_count', 0) + item.get('coverage_count', 0) for item in result['evaluations'])
        whole = stored.get(scan_id, 0) == announced and (scan_id in recorded or announced == 0)
        state = 'COMPLETE' if whole else 'INCOMPLETE'
        connection.execute(_scans.update().where(_scans.c.id == scan_id).values(result={**result, 'memory': state}))
        if whole:
            complete += 1
        else:
            incomplete.append(f'{scan_id} ({stored.get(scan_id, 0)}/{announced} faits)')
    _say(f'{complete} analyses complètes, {len(incomplete)} interrompues pendant la consolidation.')
    for item in incomplete:
        _say(f'  interrompue, gardée mais plus proposée : {item}')


def downgrade():
    connection = op.get_bind()
    for scan_id, result in connection.execute(sa.select(_scans.c.id, _scans.c.result)).all():
        if 'memory' in result:
            kept = {key: value for key, value in result.items() if key != 'memory'}
            connection.execute(_scans.update().where(_scans.c.id == scan_id).values(result=kept))
