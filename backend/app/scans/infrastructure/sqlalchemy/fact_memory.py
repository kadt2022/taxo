"""Versioned fact memory: one identity per fact, one occurrence per analysis (TAXO-01E-A).

Not wired yet: the application still uses `analysis_facts` until the migration of 01E-C. The whole
`AnalysisFacts` port is implemented: `add`, `query` (01E-A) and the one-hop traversal `neighbor`,
`has_reference`, `revision` (01E-B), with the order of `analysis_facts`. Ranks belong to the
occurrence in one adjacency (analysis, anchor, relation, direction): a batch ranks again only the
adjacencies it touches (01E-B2). The ordering keys are computed from the identity row and a fixed
occurrence fingerprint; they are never stored.

Filters on kind, subject, relation and object compare the spelling of the submitted fact, as
`analysis_facts` does: the migration of storage does not change what `query` means. The canonical
(NFC) column narrows the search through its index; the submitted spelling decides.
"""
import hashlib
import unicodedata

from sqlalchemy import (JSON, BigInteger, Boolean, Column, ForeignKey, Index, Integer, String, Text, UniqueConstraint,
                        and_, bindparam, func, or_, select, tuple_, update)
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.orm import Session

from app.evaluations.domain.capability import UNREAD_COVERAGE, unread_reasons
from app.facts import is_reference
from app.facts.domain.diagnostic import category_counts
from app.facts.domain.provenance import EXECUTABLE, ProducerExecution
from app.neighborhood.domain.traversal import Adjacent
from app.platform.database.base import Base
from app.scans.domain.fact_order import occurrence_fingerprint, order_key
from app.scans.domain.occurrence import EVIDENCE_FIELDS, Occurrence, OccurrenceError, rebuild, split
from app.scans.infrastructure.sqlalchemy import reference_index

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
    # No B-tree on subject or object: references have no length limit, and a PostgreSQL index entry has
    # one. Filters run within one analysis, from its occurrences; traversal uses fixed-size digests.
    __table_args__ = (Index('ix_fact_identities_relation', 'relation', 'kind'),)


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
    # Traversal of assertions only: relation, ranks and the object anchor are left empty for absences and
    # coverage. A coverage keeps the anchor of its subject (TAXO-01J): what is unread about a node is read
    # by that node, through the same fixed-size index, never by walking the analysis.
    relation = Column(String)
    subject_hash = Column(String(64))
    object_hash = Column(String(64))
    occurrence_hash = Column(String(64))
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
    # The span of a call site within its lines (TAXO-01K): UTF-8 byte columns, end exclusive.
    column_start = Column(Integer)
    column_end = Column(Integer)
    role = Column(String)
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


def _references(facts):
    """Les références que nomment des assertions (leur sujet, et leur objet quand c'en est une), telles qu'elles
    ont été soumises : c'est cette orthographe que le parcours accepte comme ancre. La recherche, elle, compare
    leur forme canonique."""
    for fact in facts:
        if fact['kind'] == 'ASSERTION':
            yield fact['subject']
            if isinstance(fact.get('object'), str) and is_reference(fact['object']):
                yield fact['object']


def _anchors(fact):
    if fact['kind'] == 'COVERAGE':
        return {'subject_hash': _reference_hash(fact.get('subject'))}
    if fact['kind'] != 'ASSERTION':
        return {}
    return {'relation': fact.get('relation'), 'subject_hash': _reference_hash(fact.get('subject')),
            'object_hash': _reference_hash(fact.get('object')), 'occurrence_hash': occurrence_fingerprint(fact)}


# (anchor field, anchor fingerprint, rank, neighbour field) of each traversal direction.
_SIDES = {'OUTGOING': ('subject', FactOccurrenceRow.subject_hash, FactOccurrenceRow.outgoing_rank, 'object'),
          'INCOMING': ('object', FactOccurrenceRow.object_hash, FactOccurrenceRow.incoming_rank, 'subject')}
_GROUPS = 500


def _adjacency_rows(db, scan_id, direction, groups):
    """Occurrences of the given adjacencies only, with what their order needs and nothing else."""
    _, fingerprint, _, neighbour = _SIDES[direction]
    occurrence = FactOccurrenceRow
    return db.execute(
        select(occurrence.id, fingerprint.label('anchor'), occurrence.relation,
               getattr(FactIdentityRow, neighbour).label('reference'), occurrence.identity_hash,
               occurrence.occurrence_hash)
        .join(FactIdentityRow, FactIdentityRow.identity_hash == occurrence.identity_hash)
        .where(occurrence.scan_id == scan_id, tuple_(fingerprint, occurrence.relation).in_(groups))).all()


def _rank_adjacencies(db, scan_id, anchors):
    """Rank again, from 1, each adjacency touched by the batch; the others are not read."""
    for direction, (_, fingerprint, rank, _) in _SIDES.items():
        groups = sorted({(item[fingerprint.key], item['relation']) for item in anchors if item.get('relation')})
        for start in range(0, len(groups), _GROUPS):
            members = {}
            for row in _adjacency_rows(db, scan_id, direction, groups[start:start + _GROUPS]):
                members.setdefault((row.anchor, row.relation), []).append(row)
            values = []
            for adjacency in members.values():
                # The identity row keeps the canonical (NFC) reference: the key of adjacency_keys.
                adjacency.sort(key=lambda row: order_key(row.reference, row.identity_hash.removeprefix('sha256:'),
                                                         row.occurrence_hash))
                values += [{'_id': row.id, '_rank': position} for position, row in enumerate(adjacency, 1)]
            db.execute(update(FactOccurrenceRow.__table__).where(FactOccurrenceRow.id == bindparam('_id'))
                       .values({rank.key: bindparam('_rank')}), values)


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
            # Serialize the writers of one analysis before reading it: ranks and rows commit together.
            # A no-op UPDATE locks the row on PostgreSQL (as FOR UPDATE) and takes the write lock at once
            # on SQLite, which ignores FOR UPDATE.
            locked = db.execute(update(AnalysisSnapshotRow.__table__).where(AnalysisSnapshotRow.scan_id == scan_id)
                                .values(scan_id=AnalysisSnapshotRow.scan_id))
            if locked.rowcount == 0:
                raise OccurrenceError("L'instantané de l'analyse n'est pas enregistré.")
            recorded = db.get(AnalysisSnapshotRow, scan_id)
            executions = {row.execution_id: row for row in db.scalars(
                select(ProducerExecutionRow).where(ProducerExecutionRow.scan_id == scan_id))}
            # One pass over `facts`: any iterable is accepted, a generator included.
            prepared = [(fact, split(fact, recorded.snapshot), _producer(fact, evaluator_id, executions))
                        for fact in facts]
            identities = {occurrence.identity_hash: occurrence.identity for _, occurrence, _ in prepared}
            if identities:
                _insert_new_identities(db, [
                    {'identity_hash': key, 'kind': identity['kind'], 'subject': identity.get('subject'),
                     'relation': identity.get('relation'), 'object': identity.get('object'), 'identity': identity}
                    for key, identity in identities.items()])
            # One flush per table for the whole batch. The session keeps each row object bound to the id
            # it receives, and inserts the rows in the order they were added: submission order, which
            # query() gives back through the occurrence id.
            anchors = [_anchors(fact) for fact, _, _ in prepared]
            rows = [FactOccurrenceRow(scan_id=scan_id, identity_hash=occurrence.identity_hash, execution=execution,
                                      human_producer_id=human, status=occurrence.status,
                                      validity=occurrence.validity, raw_identity=occurrence.raw_identity,
                                      details=occurrence.details or None,
                                      has_evidence=occurrence.evidence is not None, **anchor)
                    for (_, occurrence, (execution, human)), anchor in zip(prepared, anchors)]
            db.add_all(rows)
            db.flush()
            db.add_all(FactEvidenceRow(occurrence=row.id, position=position, **item)
                       for row, (_, occurrence, _) in zip(rows, prepared)
                       for position, item in enumerate(occurrence.evidence or ()))
            db.flush()
            _rank_adjacencies(db, scan_id, anchors)
            reference_index.record(db, reference_index.rows(scan_id, _references(fact for fact, _, _ in prepared)))
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
            return [fact for _, fact in self.load_rows(db, scan_id, statement.order_by(occurrence.id))]

    def executions(self, scan_id):
        """The producer executions recorded for the analysis, in recording order: one row each, no fact read."""
        with Session(self.engine) as db:
            return [row.execution() for row in db.scalars(select(ProducerExecutionRow).where(
                ProducerExecutionRow.scan_id == scan_id).order_by(ProducerExecutionRow.id))]

    def objects(self, scan_id, relation):
        """The distinct objects of one relation in the analysis, sorted, without rebuilding any fact."""
        occurrence, identity = FactOccurrenceRow, FactIdentityRow
        with Session(self.engine) as db:
            return sorted(db.scalars(select(identity.object).distinct()
                                     .join(occurrence, occurrence.identity_hash == identity.identity_hash)
                                     .where(occurrence.scan_id == scan_id, identity.kind == 'ASSERTION',
                                            identity.relation == relation)).all())

    def neighbor(self, scan_id, root, relation, direction, after=''):
        """One indexed adjacent occurrence, as (rank, fact). Never materialize the complete adjacency."""
        found = self.neighbors(scan_id, root, relation, direction, after, 1)
        return (found[0].key, found[0].fact) if found else None

    def neighbors(self, scan_id, root, relation, direction, after, limit):
        """At most `limit` adjacent occurrences, in rank order, after `after`: never the whole adjacency. Each one
        with its rank, its occurrence (stable in the analysis) and its identity.

        One statement: the page is chosen by the anchor index alone, in its order and under its limit, then its
        occurrences are loaded. The bound holds whatever plan the database picks (TAXO-01J, tranche F: with real
        statistics, PostgreSQL joined every identity of a high-degree anchor before the limit). The spelling is
        checked on the loaded page: it only rules out another reference sharing the anchor fingerprint, and were
        it to drop an occurrence, the read goes on after the page, so the result stays exact."""
        anchor, fingerprint, rank, _ = _SIDES[direction]
        found, position = [], int(after or '0')
        with Session(self.engine) as db:
            while len(found) < limit:
                wanted = limit - len(found)
                page = (select(FactOccurrenceRow.id)
                        .where(FactOccurrenceRow.scan_id == scan_id, fingerprint == _reference_hash(root),
                               FactOccurrenceRow.relation == relation, rank > position)
                        .order_by(rank).limit(wanted))
                loaded = self.load_rows(db, scan_id, _facts_of(scan_id).add_columns(rank)
                                        .where(FactOccurrenceRow.id.in_(page)).order_by(rank))
                found += [(row, fact) for row, fact in loaded if fact.get(anchor) == root]
                if len(loaded) < wanted:
                    break
                position = loaded[-1][0][3]
        return [Adjacent(str(row[3]), str(row[0].id), row[0].identity_hash, fact) for row, fact in found]

    def occurrence(self, scan_id, key):
        """The fact of one occurrence of the analysis, by the key `neighbors` gives; None if it has none."""
        if not (isinstance(key, str) and key.isascii() and key.isdigit() and len(key) <= 19):
            return None
        statement = _facts_of(scan_id).where(FactOccurrenceRow.id == int(key))
        with Session(self.engine) as db:
            found = self.load_rows(db, scan_id, statement)
        return found[0][1] if found else None

    def unread(self, scan_id, references):
        """The coverage of the analysis that says one of these references was not read (NOT_INTERPRETED,
        READ_ERROR): its subject, type, producer and the closed reasons of its diagnostic. Read by subject anchor,
        a batch of references at a time."""
        occurrence, identity, execution = FactOccurrenceRow, FactIdentityRow, ProducerExecutionRow
        wanted = sorted(set(references))
        found = []
        with Session(self.engine) as db:
            for start in range(0, len(wanted), _GROUPS):
                chunk = wanted[start:start + _GROUPS]
                rows = db.execute(
                    select(identity.subject, occurrence.raw_identity, identity.identity, execution.producer_id,
                           occurrence.human_producer_id, occurrence.details)
                    .join(identity, identity.identity_hash == occurrence.identity_hash)
                    .outerjoin(execution, execution.id == occurrence.execution)
                    .where(occurrence.scan_id == scan_id, occurrence.relation.is_(None),
                           occurrence.subject_hash.in_([_reference_hash(item) for item in chunk]),
                           identity.kind == 'COVERAGE')).all()
                asked = set(chunk)
                for canonical, raw, value, machine, human, details in rows:
                    # The spelling as submitted, the one the anchor was computed from and a tile renders; it
                    # also rules out another reference sharing the anchor fingerprint.
                    subject = (raw or {}).get('subject', canonical)
                    if subject in asked and value.get('coverage_type') in UNREAD_COVERAGE:
                        found.append({'subject': subject, 'coverage_type': value['coverage_type'],
                                      'producer': machine or human, 'reasons': unread_reasons(details or {}),
                                      'categories': category_counts(details or {})})
        return sorted(found, key=lambda item: (item['subject'], item['coverage_type'], item['producer'] or ''))

    def references(self, scan_id, prefix, kind, after, limit):
        """References of the analysis whose key starts with `prefix`: one range read of a fixed-size index."""
        with Session(self.engine) as db:
            return reference_index.search(db, scan_id, prefix, kind, after, limit)

    def revision(self, scan_id):
        """Append-only fact generation, read through a fixed-size index."""
        with Session(self.engine) as db:
            return db.scalar(select(FactOccurrenceRow.id).where(FactOccurrenceRow.scan_id == scan_id)
                             .order_by(FactOccurrenceRow.id.desc()).limit(1)) or 0

    def has_reference(self, scan_id, root):
        occurrence = FactOccurrenceRow
        with Session(self.engine) as db:
            for anchor, fingerprint, _, _ in _SIDES.values():
                found = db.scalar(
                    select(occurrence.id).join(FactIdentityRow, FactIdentityRow.identity_hash == occurrence.identity_hash)
                    .where(occurrence.scan_id == scan_id, fingerprint == _reference_hash(root),
                           occurrence.relation.is_not(None),
                           _spelled(occurrence, getattr(FactIdentityRow, anchor), anchor, root)).limit(1))
                if found is not None:
                    return True
        return False

    def load_rows(self, db, scan_id, statement):
        """(row, fact) for each selected occurrence, the fact rebuilt exactly as it was submitted."""
        rows = db.execute(statement).all()
        if not rows:
            return []
        snapshot = db.get(AnalysisSnapshotRow, scan_id).snapshot
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
