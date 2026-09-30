"""Versioned fact memory: one identity per fact, one occurrence per analysis (TAXO-01E-A).

Not wired yet: the application still uses `analysis_facts` until the migration of 01E-C. This
implementation covers `add` and `query` of the `AnalysisFacts` port; traversal comes with 01E-B.

Filters on kind, subject, relation and object compare the canonical identity (NFC). The facts
returned are those submitted, exactly, with their own spelling.
"""
from sqlalchemy import (JSON, Boolean, Column, ForeignKey, Index, Integer, String, Text, UniqueConstraint,
                        func, select)
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.orm import Session

from app.facts.domain.provenance import EXECUTABLE, ProducerExecution
from app.platform.database.base import Base
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
    raw_identity = Column(JSON)
    details = Column(JSON)
    has_evidence = Column(Boolean, nullable=False)
    __table_args__ = (Index('ix_fact_occurrences_analysis', 'scan_id', 'id'),
                      Index('ix_fact_occurrences_identity', 'identity_hash', 'scan_id'))


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
            for occurrence, (execution, human) in prepared:
                row = FactOccurrenceRow(scan_id=scan_id, identity_hash=occurrence.identity_hash, execution=execution,
                                        human_producer_id=human, status=occurrence.status,
                                        validity=occurrence.validity, raw_identity=occurrence.raw_identity,
                                        details=occurrence.details or None,
                                        has_evidence=occurrence.evidence is not None)
                db.add(row)
                db.flush()
                db.add_all(FactEvidenceRow(occurrence=row.id, position=position, **item)
                           for position, item in enumerate(occurrence.evidence or ()))
            db.commit()

    def query(self, scan_id, **filters):
        occurrence, identity, execution = FactOccurrenceRow, FactIdentityRow, ProducerExecutionRow
        statement = (select(occurrence, identity.identity, execution)
                     .join(identity, identity.identity_hash == occurrence.identity_hash)
                     .outerjoin(execution, execution.id == occurrence.execution)
                     .where(occurrence.scan_id == scan_id))
        if filters.get('evaluator_id') is not None:
            statement = statement.where(func.coalesce(execution.producer_id, occurrence.human_producer_id)
                                        == filters['evaluator_id'])
        for name in ('kind', 'subject', 'relation', 'object'):
            if filters.get(name) is not None:
                statement = statement.where(getattr(identity, name) == filters[name])
        with Session(self.engine) as db:
            recorded = db.get(AnalysisSnapshotRow, scan_id)
            rows = db.execute(statement.order_by(occurrence.id)).all()
            evidence = self._evidence(db, [row.id for row, _, _ in rows if row.has_evidence])
        return [rebuild(Occurrence(row.identity_hash, stored, row.raw_identity, row.status, row.validity,
                                   evidence.get(row.id, ()) if row.has_evidence else None, row.details or {}),
                        recorded.snapshot,
                        producer.execution().produced_by() if producer is not None
                        else {'producer_type': 'HUMAN', 'producer_id': row.human_producer_id})
                for row, stored, producer in rows]

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
