"""Faits produits par une analyse globale, conserves pour etre interroges apres coup (TAXO-EVAL-02).

Stockage minimal : une ligne par fait, avec les colonnes qui servent a filtrer. Depuis TAXO-01E, Taxo
ecrit et lit la memoire versionnee (fact_memory.py) ; cette table reste en secours, n'est plus alimentee,
et sert de reference aux tests d'equivalence jusqu'a son retrait par une migration ulterieure.
"""
import hashlib
import json

from sqlalchemy import (JSON, BigInteger, Column, ForeignKey, Index, Integer, String, Text,
                        bindparam, column, select, table, update)
from sqlalchemy.orm import Session
from app.platform.database.base import Base
from app.evaluations.domain.capability import UNREAD_COVERAGE
from app.neighborhood.domain.traversal import Adjacent
from app.scans.domain.fact_order import adjacency_keys


class AnalysisFactRow(Base):
    __tablename__ = 'analysis_facts'
    id = Column(Integer, primary_key=True, autoincrement=True)
    scan_id = Column(String, ForeignKey('scans.id'), nullable=False, index=True)
    evaluator_id = Column(String, nullable=False)
    kind = Column(String, nullable=False)
    subject = Column(String)
    relation = Column(String)
    object = Column(String)
    fact = Column(JSON, nullable=False)
    outgoing_key = Column(Text)
    incoming_key = Column(Text)
    subject_hash = Column(String(64))
    object_hash = Column(String(64))
    outgoing_rank = Column(BigInteger)
    incoming_rank = Column(BigInteger)
    __table_args__ = (
        Index('ix_analysis_facts_revision', 'scan_id', 'id'),
        Index('ix_analysis_facts_outgoing', 'scan_id', 'kind', 'subject_hash', 'relation', 'outgoing_rank'),
        Index('ix_analysis_facts_incoming', 'scan_id', 'kind', 'object_hash', 'relation', 'incoming_rank'),
    )


def _reference_hash(reference):
    return hashlib.sha256((reference or '').encode()).hexdigest()


def _rank_analysis(db, scan_id):
    # Ingestion cost only. The unbounded ordering keys are never B-tree entries.
    row = AnalysisFactRow
    records = db.execute(select(row.id, row.outgoing_key, row.incoming_key)
                         .where(row.scan_id == scan_id)).all()
    for position, side in ((1, 'outgoing'), (2, 'incoming')):
        values = [{'_id': record.id, '_rank': rank} for rank, record in
                  enumerate(sorted(records, key=lambda item: item[position]), 1)]
        if values:
            db.execute(update(row.__table__).where(row.id == bindparam('_id'))
                       .values({f'{side}_rank': bindparam('_rank')}), values)


def _identity(fact):
    fields = {key: fact.get(key) for key in ('kind', 'subject', 'relation', 'object', 'qualifiers')}
    return 'fields:' + hashlib.sha256(json.dumps(fields, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


_FILTERS = ('evaluator_id', 'kind', 'subject', 'relation', 'object')


class SqlAlchemyAnalysisFacts:
    def __init__(self, engine):
        self.engine = engine

    def add(self, scan_id, evaluator_id, facts):
        with Session(self.engine) as db:
            # Serialize writers to this analysis; ranks and new rows commit atomically.
            scans = table('scans', column('id'))
            db.execute(select(scans.c.id).where(scans.c.id == scan_id).with_for_update()).first()
            for fact in facts:
                outgoing, incoming = adjacency_keys(fact)
                db.add(AnalysisFactRow(scan_id=scan_id, evaluator_id=evaluator_id, kind=fact['kind'],
                                      subject=fact.get('subject'), relation=fact.get('relation'),
                                      object=fact.get('object'), fact=fact,
                                      outgoing_key=outgoing, incoming_key=incoming,
                                      subject_hash=_reference_hash(fact.get('subject')),
                                      object_hash=_reference_hash(fact.get('object'))))
            db.flush()
            _rank_analysis(db, scan_id)
            db.commit()

    def neighbor(self, scan_id, root, relation, direction, after=''):
        """One indexed adjacent occurrence, as (rank, fact). Never materialize the complete adjacency."""
        found = self.neighbors(scan_id, root, relation, direction, after, 1)
        return (found[0].key, found[0].fact) if found else None

    def neighbors(self, scan_id, root, relation, direction, after, limit):
        """At most `limit` adjacent facts, in rank order, after `after`: one indexed read. This table keeps no
        identity: the key that groups the occurrences of one fact is computed from its identifying fields."""
        row = AnalysisFactRow
        anchor, fingerprint, rank = (
            (row.subject, row.subject_hash, row.outgoing_rank) if direction == 'OUTGOING'
            else (row.object, row.object_hash, row.incoming_rank))
        statement = select(rank, row.id, row.fact).where(
            row.scan_id == scan_id, row.kind == 'ASSERTION', fingerprint == _reference_hash(root),
            anchor == root, row.relation == relation, rank > int(after or '0'))
        with Session(self.engine) as db:
            found = db.execute(statement.order_by(rank).limit(limit)).all()
        return [Adjacent(str(position), str(identifier), _identity(fact), fact) for position, identifier, fact in found]

    def occurrence(self, scan_id, key):
        """The fact of one row of the analysis, by the key `neighbors` gives; None if it has none."""
        if not (isinstance(key, str) and key.isascii() and key.isdigit() and len(key) <= 19):
            return None
        row = AnalysisFactRow
        with Session(self.engine) as db:
            return db.scalar(select(row.fact).where(row.scan_id == scan_id, row.id == int(key)))

    def unread(self, scan_id, references):
        """The coverage of the analysis that says one of these references was not read, by subject anchor."""
        row = AnalysisFactRow
        wanted = sorted(set(references))
        found = []
        with Session(self.engine) as db:
            for start in range(0, len(wanted), 500):
                chunk = wanted[start:start + 500]
                for fact in db.scalars(select(row.fact).where(
                        row.scan_id == scan_id, row.kind == 'COVERAGE',
                        row.subject_hash.in_([_reference_hash(item) for item in chunk]), row.subject.in_(chunk))):
                    if fact.get('coverage_type') in UNREAD_COVERAGE:
                        found.append({'subject': fact['subject'], 'coverage_type': fact['coverage_type'],
                                      'producer': fact.get('produced_by', {}).get('producer_id')})
        return sorted(found, key=lambda item: (item['subject'], item['coverage_type'], item['producer'] or ''))

    def revision(self, scan_id):
        """Append-only fact generation, read through a fixed-size index."""
        row = AnalysisFactRow
        with Session(self.engine) as db:
            return db.scalar(select(row.id).where(row.scan_id == scan_id)
                             .order_by(row.id.desc()).limit(1)) or 0

    def has_reference(self, scan_id, root):
        row = AnalysisFactRow
        with Session(self.engine) as db:
            for anchor, fingerprint in ((row.subject, row.subject_hash), (row.object, row.object_hash)):
                found = db.scalar(select(row.id).where(
                    row.scan_id == scan_id, row.kind == 'ASSERTION',
                    fingerprint == _reference_hash(root), anchor == root).limit(1))
                if found is not None:
                    return True
        return False

    def objects(self, scan_id, relation):
        """The distinct objects of one relation in the analysis, sorted, as the versioned memory gives them."""
        row = AnalysisFactRow
        with Session(self.engine) as db:
            return sorted(db.scalars(select(row.object).distinct().where(
                row.scan_id == scan_id, row.kind == 'ASSERTION', row.relation == relation)).all())

    def query(self, scan_id, **filters):
        statement = select(AnalysisFactRow.fact).where(AnalysisFactRow.scan_id == scan_id)
        for name in _FILTERS:
            if filters.get(name) is not None:
                statement = statement.where(getattr(AnalysisFactRow, name) == filters[name])
        with Session(self.engine) as db:
            return list(db.scalars(statement.order_by(AnalysisFactRow.id)))
