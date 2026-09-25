"""Faits produits par une analyse globale, conserves pour etre interroges apres coup (TAXO-EVAL-02).

Stockage minimal : une ligne par fait, avec les colonnes qui servent a filtrer. Ce n'est pas la memoire
versionnee de TAXO-01E : les faits restent attaches a l'analyse qui les a produits.
"""
from sqlalchemy import JSON, Column, ForeignKey, Integer, String, select
from sqlalchemy.orm import Session
from app.platform.database.base import Base


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


_FILTERS = ('evaluator_id', 'kind', 'subject', 'relation', 'object')


class SqlAlchemyAnalysisFacts:
    def __init__(self, engine):
        self.engine = engine

    def add(self, scan_id, evaluator_id, facts):
        with Session(self.engine) as db:
            db.add_all(AnalysisFactRow(scan_id=scan_id, evaluator_id=evaluator_id, kind=fact['kind'],
                                       subject=fact.get('subject'), relation=fact.get('relation'),
                                       object=fact.get('object'), fact=fact) for fact in facts)
            db.commit()

    def query(self, scan_id, **filters):
        statement = select(AnalysisFactRow.fact).where(AnalysisFactRow.scan_id == scan_id)
        for name in _FILTERS:
            if filters.get(name) is not None:
                statement = statement.where(getattr(AnalysisFactRow, name) == filters[name])
        with Session(self.engine) as db:
            return list(db.scalars(statement.order_by(AnalysisFactRow.id)))
