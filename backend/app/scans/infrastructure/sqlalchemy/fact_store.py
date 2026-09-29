"""Faits produits par une analyse globale, conserves pour etre interroges apres coup (TAXO-EVAL-02).

Stockage minimal : une ligne par fait, avec les colonnes qui servent a filtrer. Ce n'est pas la memoire
versionnee de TAXO-01E : les faits restent attaches a l'analyse qui les a produits.
"""
from sqlalchemy import JSON, Column, ForeignKey, Index, Integer, String, Text, select
from sqlalchemy.orm import Session
from app.platform.database.base import Base
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
    __table_args__ = (
        Index('ix_analysis_facts_outgoing', 'scan_id', 'kind', 'subject', 'relation', 'outgoing_key'),
        Index('ix_analysis_facts_incoming', 'scan_id', 'kind', 'object', 'relation', 'incoming_key'),
    )


_FILTERS = ('evaluator_id', 'kind', 'subject', 'relation', 'object')


class SqlAlchemyAnalysisFacts:
    def __init__(self, engine):
        self.engine = engine

    def add(self, scan_id, evaluator_id, facts):
        with Session(self.engine) as db:
            for fact in facts:
                outgoing, incoming = adjacency_keys(fact)
                db.add(AnalysisFactRow(scan_id=scan_id, evaluator_id=evaluator_id, kind=fact['kind'],
                                      subject=fact.get('subject'), relation=fact.get('relation'),
                                      object=fact.get('object'), fact=fact,
                                      outgoing_key=outgoing, incoming_key=incoming))
            db.commit()

    def neighbor(self, scan_id, root, relation, direction, after=''):
        """One indexed adjacent occurrence. Never materialize the complete adjacency."""
        row = AnalysisFactRow
        anchor, key = ((row.subject, row.outgoing_key) if direction == 'OUTGOING'
                       else (row.object, row.incoming_key))
        statement = select(key, row.fact).where(row.scan_id == scan_id, row.kind == 'ASSERTION',
                                                anchor == root, row.relation == relation, key > after)
        with Session(self.engine) as db:
            found = db.execute(statement.order_by(key).limit(1)).first()
            return tuple(found) if found else None

    def has_reference(self, scan_id, root):
        row = AnalysisFactRow
        with Session(self.engine) as db:
            for anchor in (row.subject, row.object):
                found = db.scalar(select(row.id).where(row.scan_id == scan_id, row.kind == 'ASSERTION',
                                                       anchor == root).limit(1))
                if found is not None:
                    return True
        return False

    def query(self, scan_id, **filters):
        statement = select(AnalysisFactRow.fact).where(AnalysisFactRow.scan_id == scan_id)
        for name in _FILTERS:
            if filters.get(name) is not None:
                statement = statement.where(getattr(AnalysisFactRow, name) == filters[name])
        with Session(self.engine) as db:
            return list(db.scalars(statement.order_by(AnalysisFactRow.id)))
