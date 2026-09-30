"""Versioned fact memory: one identity per fact, one occurrence per analysis (TAXO-01E-A).

Not wired yet: the application still uses `analysis_facts` until the migration of 01E-C. The whole
`AnalysisFacts` port is implemented: `add`, `query` (01E-A) and the one-hop traversal `neighbor`,
`has_reference`, `revision` (01E-B), with the order of `analysis_facts`. Ranks belong to the
occurrence in its analysis; the ordering keys are computed at ingestion and never stored.

Filters on kind, subject, relation and object compare the spelling of the submitted fact, as
`analysis_facts` does: the migration of storage does not change what `query` means. The canonical
(NFC) column narrows the search through its index; the submitted spelling decides.
"""
import hashlib
import unicodedata

from sqlalchemy import (JSON, BigInteger, Boolean, Column, ForeignKey, Index, Integer, String, Text, UniqueConstraint,
                        and_, bindparam, func, or_, select, update)
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.orm import Session

from app.facts.domain.provenance import EXECUTABLE, ProducerExecution
from app.platform.database.base import Base
from app.scans.domain.fact_order import adjacency_keys
from app.scans.domain.occurrence import EVIDENCE_FIELDS, Occurrence, OccurrenceError, rebuild, split

_SCAN = 'scans.id'


class AnalysisSnapshotRow(Base):
    __tablename__ = 'analysis_snapshots'
    scan_id = Column(String, ForeignKey(_SCAN), primary_key=True)
    snapshot = Column(JSON, nullable=False)


class ProducerExecutionRow(Base):
    __tablename__ = 'producer_executions'
    id = Column(Integer, primary_key=True, autoincrement=True)
    scan_id = Column(String, ForeignKey(_SCAN), nullable=False)
    execution_id = Column(String, nullable=False)
    producer_type = Column(String, nullable=False)
    producer_id = Column(String, nullable=False)
    producer_version = Column(String, nullable=False)
    catalog_id = Column(String)
    catalog_version = Column(String)
    __table_args__ = (UniqueConstraint('scan_id', 'execution_id', name='uq_producer_executions_scan_execution'),)

    def execution(self):
        return ProducerExecution(self.producer_type, self.producer_id, self.producer_version,
                                 self.execution_id, self.catalog_id, self.catalog_version)


class FactIdentityRow(Base):
    __tablename__ = 'fact_identities'
    identity_hash = Column(String(71), primary_key=True)
    kind = Column(String, nullable=False)
    subject = Column(Text)
    relation = Column(String)
    object = Column(Text)
    identity = Column(JSON, nullable=False)
    __table_args__ = (Index('ix_fact_identities_subject', 'subject'),
                      Index('ix_fact_identities_object', 'object'),
                      Index('ix_fact_identities_relation', 'relation', 'kind'))


class FactOccurrenceRow(Base):
    __tablename__ = 'fact_occurrences'
    id = Column(Integer, primary_key=True, autoincrement=True)
    scan_id = Column(String, ForeignKey(_SCAN), nullable=False)
    identity_hash = Column(String(71), ForeignKey('fact_identities.identity_hash'), nullable=False)
    execution = Column(Integer, ForeignKey('producer_executions.id'))
    human_producer_id = Column(String)
    status = Column(String, nullable=False)
    validity = Column(String, nullable=False)
    raw_identity = Column(JSON(none_as_null=True))
    details = Column(JSON(none_as_null=True))
    has_evidence = Column(Boolean, nullable=False)
    # Traversal of assertions only: relation and anchors are left empty for absences and coverage.
    relation = Column(String)
    subject_hash = Column(String(64))
    object_hash = Column(String(64))
    outgoing_rank = Column(BigInteger)
    incoming_rank = Column(BigInteger)
    __table_args__ = (Index('ix_fact_occurrences_analysis', 'scan_id', 'id'),
                      Index('ix_fact_occurrences_identity', 'identity_hash', 'scan_id'),
                      Index('ix_fact_occurrences_outgoing', 'scan_id', 'subject_hash', 'relation', 'outgoing_rank'),
                      Index('ix_fact_occurrences_incoming', 'scan_id', 'object_hash', 'relation', 'incoming_rank'))


class FactEvidenceRow(Base):
    __tablename__ = 'fact_evidence'
    id = Column(Integer, primary_key=True, autoincrement=True)
    occurrence = Column(Integer, ForeignKey('fact_occurrences.id'), nullable=False)
    position = Column(Integer, nullable=False)
    path = Column(Text)
    line_start = Column(Integer)
    line_end = Column(Integer)
    symbol = Column(Text)
    method = Column(String)
    content_hash = Column(String)
    object = Column(String)
    __table_args__ = (Index('ix_fact_evidence_occurrence', 'occurrence', 'position'),)


def _insert_new_identities(db, rows):
    dialect = postgresql if db.get_bind().dialect.name == 'postgresql' else sqlite
    statement = dialect.insert(FactIdentityRow.__table__).on_conflict_do_nothing(index_elements=['identity_hash'])
    db.execute(statement, rows)


def _producer(fact, evaluator_id, executions):
    """Execution row id, or HUMAN producer id; never an execution invented from the fact."""
    produced_by = fact['produced_by']
    if produced_by.get('producer_id') != evaluator_id:
        raise OccurrenceError("Le producteur du fait n'est pas celui qui l'enregistre.")
    if produced_by.get('producer_type') in EXECUTABLE:
        row = executions.get(produced_by.get('execution_id'))
        if row is None or row.execution().produced_by() != produced_by:
            raise OccurrenceError("Le fait ne correspond à aucune exécution enregistrée pour cette analyse.")
        return row.id, None
    if produced_by != {'producer_type': 'HUMAN', 'producer_id': evaluator_id}:
        raise OccurrenceError('Producteur inconnu.')
    return None, evaluator_id


def _reference_hash(reference):
    return hashlib.sha256((reference or '').encode()).hexdigest()


def _anchors(fact):
    if fact['kind'] != 'ASSERTION':
        return {}
    return {'relation': fact.get('relation'), 'subject_hash': _reference_hash(fact.get('subject')),
            'object_hash': _reference_hash(fact.get('object'))}


# (anchor field, anchor fingerprint, rank) of each traversal direction.
_SIDES = {'OUTGOING': ('subject', FactOccurrenceRow.subject_hash, FactOccurrenceRow.outgoing_rank),
          'INCOMING': ('object', FactOccurrenceRow.object_hash, FactOccurrenceRow.incoming_rank)}


def _spelled(occurrence, canonical, name, value):
    """Same spelling as submitted: the canonical form when it was kept as is, the raw one otherwise."""
    if not isinstance(value, str):
        return canonical == value
    return and_(canonical == unicodedata.normalize('NFC', value),
                or_(and_(occurrence.raw_identity.is_(None), canonical == value),
                    occurrence.raw_identity[name].as_string() == value))


def _facts_of(scan_id):
    occurrence, identity, execution = FactOccurrenceRow, FactIdentityRow, ProducerExecutionRow
    return (select(occurrence, identity.identity, execution)
            .join(identity, identity.identity_hash == occurrence.identity_hash)
            .outerjoin(execution, execution.id == occurrence.execution)
            .where(occurrence.scan_id == scan_id))


class SqlAlchemyFactMemory:
    def __init__(self, engine):
        self.engine = engine

    def record_snapshot(self, scan_id, snapshot):
        with Session(self.engine) as db:
            known = db.get(AnalysisSnapshotRow, scan_id)
            if known is None:
                db.add(AnalysisSnapshotRow(scan_id=scan_id, snapshot=dict(snapshot)))
                db.commit()
            elif known.snapshot != snapshot:
                raise OccurrenceError("L'analyse a déjà un autre instantané.")

    def record_execution(self, scan_id, execution):
        with Session(self.engine) as db:
            known = db.scalar(select(ProducerExecutionRow).where(
                ProducerExecutionRow.scan_id == scan_id, ProducerExecutionRow.execution_id == execution.execution_id))
            if known is None:
                db.add(ProducerExecutionRow(scan_id=scan_id, **vars(execution)))
                db.commit()
            elif known.execution() != execution:
                raise OccurrenceError('Cette exécution est déjà enregistrée autrement pour cette analyse.')

    def add(self, scan_id, evaluator_id, facts):
        """All or nothing: one refused fact and nothing of the batch is written."""
        with Session(self.engine) as db:
            recorded = db.get(AnalysisSnapshotRow, scan_id)
            if recorded is None:
                raise OccurrenceError("L'instantané de l'analyse n'est pas enregistré.")
            executions = {row.execution_id: row for row in db.scalars(
                select(ProducerExecutionRow).where(ProducerExecutionRow.scan_id == scan_id))}
            prepared = [(split(fact, recorded.snapshot), _producer(fact, evaluator_id, executions)) for fact in facts]
            identities = {occurrence.identity_hash: occurrence.identity for occurrence, _ in prepared}
            if identities:
                _insert_new_identities(db, [
                    {'identity_hash': key, 'kind': identity['kind'], 'subject': identity.get('subject'),
                     'relation': identity.get('relation'), 'object': identity.get('object'), 'identity': identity}
                    for key, identity in identities.items()])
            for fact, (occurrence, (execution, human)) in zip(facts, prepared):
                row = FactOccurrenceRow(scan_id=scan_id, identity_hash=occurrence.identity_hash, execution=execution,
                                        human_producer_id=human, status=occurrence.status,
                                        validity=occurrence.validity, raw_identity=occurrence.raw_identity,
                                        details=occurrence.details or None,
                                        has_evidence=occurrence.evidence is not None, **_anchors(fact))
                db.add(row)
                db.flush()
                db.add_all(FactEvidenceRow(occurrence=row.id, position=position, **item)
                           for position, item in enumerate(occurrence.evidence or ()))
            db.flush()
            self._rank(db, scan_id, recorded.snapshot)
            db.commit()

    def query(self, scan_id, **filters):
        occurrence, identity, execution = FactOccurrenceRow, FactIdentityRow, ProducerExecutionRow
        statement = _facts_of(scan_id)
        if filters.get('evaluator_id') is not None:
            statement = statement.where(func.coalesce(execution.producer_id, occurrence.human_producer_id)
                                        == filters['evaluator_id'])
        for name in ('kind', 'subject', 'relation', 'object'):
            if filters.get(name) is not None:
                statement = statement.where(_spelled(occurrence, getattr(identity, name), name, filters[name]))
        with Session(self.engine) as db:
            return [fact for _, fact in self._load(db, scan_id, statement.order_by(occurrence.id))]

    def neighbor(self, scan_id, root, relation, direction, after=''):
        """One indexed adjacent occurrence. Never materialize the complete adjacency."""
        anchor, fingerprint, rank = _SIDES[direction]
        statement = (_facts_of(scan_id).add_columns(rank)
                     .where(fingerprint == _reference_hash(root), FactOccurrenceRow.relation == relation,
                            _spelled(FactOccurrenceRow, getattr(FactIdentityRow, anchor), anchor, root),
                            rank > int(after or '0'))
                     .order_by(rank).limit(1))
        with Session(self.engine) as db:
            found = self._load(db, scan_id, statement)
        return (str(found[0][0][3]), found[0][1]) if found else None

    def revision(self, scan_id):
        """Append-only fact generation, read through a fixed-size index."""
        with Session(self.engine) as db:
            return db.scalar(select(FactOccurrenceRow.id).where(FactOccurrenceRow.scan_id == scan_id)
                             .order_by(FactOccurrenceRow.id.desc()).limit(1)) or 0

    def has_reference(self, scan_id, root):
        occurrence = FactOccurrenceRow
        with Session(self.engine) as db:
            for anchor, fingerprint, _ in _SIDES.values():
                found = db.scalar(
                    select(occurrence.id).join(FactIdentityRow, FactIdentityRow.identity_hash == occurrence.identity_hash)
                    .where(occurrence.scan_id == scan_id, fingerprint == _reference_hash(root),
                           occurrence.relation.is_not(None),
                           _spelled(occurrence, getattr(FactIdentityRow, anchor), anchor, root)).limit(1))
                if found is not None:
                    return True
        return False

    def _rank(self, db, scan_id, snapshot):
        """Same rule as `analysis_facts`: the whole analysis ranked again, in its canonical key order."""
        keyed = [(row[0].id, *adjacency_keys(fact)) for row, fact in
                 self._load(db, scan_id, _facts_of(scan_id).order_by(FactOccurrenceRow.id), snapshot)]
        for position, side in ((1, 'outgoing'), (2, 'incoming')):
            values = [{'_id': item[0], '_rank': rank}
                      for rank, item in enumerate(sorted(keyed, key=lambda item: item[position]), 1)]
            if values:
                db.execute(update(FactOccurrenceRow.__table__).where(FactOccurrenceRow.id == bindparam('_id'))
                           .values({f'{side}_rank': bindparam('_rank')}), values)

    def _load(self, db, scan_id, statement, snapshot=None):
        """(row, fact) for each selected occurrence, the fact rebuilt exactly as it was submitted."""
        rows = db.execute(statement).all()
        if not rows:
            return []
        snapshot = snapshot or db.get(AnalysisSnapshotRow, scan_id).snapshot
        evidence = self._evidence(db, [row[0].id for row in rows if row[0].has_evidence])
        loaded = []
        for row in rows:
            occurrence, stored, producer = row[0], row[1], row[2]
            fact = rebuild(Occurrence(occurrence.identity_hash, stored, occurrence.raw_identity, occurrence.status,
                                      occurrence.validity,
                                      evidence.get(occurrence.id, ()) if occurrence.has_evidence else None,
                                      occurrence.details or {}),
                           snapshot,
                           producer.execution().produced_by() if producer is not None
                           else {'producer_type': 'HUMAN', 'producer_id': occurrence.human_producer_id})
            loaded.append((row, fact))
        return loaded

    @staticmethod
    def _evidence(db, occurrences, batch=500):
        found = {}
        for start in range(0, len(occurrences), batch):
            chunk = occurrences[start:start + batch]
            for item in db.scalars(select(FactEvidenceRow).where(FactEvidenceRow.occurrence.in_(chunk))
                                   .order_by(FactEvidenceRow.occurrence, FactEvidenceRow.position)):
                found.setdefault(item.occurrence, []).append(
                    {name: getattr(item, name) for name in EVIDENCE_FIELDS if getattr(item, name) is not None})
        return found
