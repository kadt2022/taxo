"""Les références d'une analyse retrouvées par leur nom (TAXO-01N, PR A2, `find_references` avec `match: NAME`).

Une projection de l'index des références (`reference_index`) : une ligne par nom sous lequel une référence se
retrouve (`app.neighborhood.domain.reference_names.name_keys`), écrite dans la même transaction que ses faits.
La recherche est une égalité sur un index B-tree de taille fixe, lue dans l'ordre de l'empreinte de la
référence et bornée par la page demandée : jamais un parcours des faits. Une référence n'a qu'une ligne par
nom : elle n'est jamais rendue deux fois.
"""
from sqlalchemy import Column, ForeignKey, Index, String, exists, select

from app.neighborhood.domain.reference_names import name_keys
from app.neighborhood.domain.references import KEY_LENGTH
from app.platform.database.base import Base
from app.scans.infrastructure.sqlalchemy.reference_index import AnalysisReferenceRow, insert_new, ordered


class AnalysisReferenceNameRow(Base):
    __tablename__ = 'analysis_reference_names'
    scan_id = Column(String, ForeignKey('scans.id'), primary_key=True)
    name_key = Column(ordered(KEY_LENGTH), primary_key=True)
    reference_hash = Column(ordered(64), primary_key=True)
    type = Column(String, nullable=False)
    __table_args__ = (Index('ix_analysis_reference_names_type', 'scan_id', 'type', 'name_key', 'reference_hash'),)


def rows(reference_rows):
    """Les noms à enregistrer pour ces lignes de l'index des références."""
    return [{'scan_id': row['scan_id'], 'name_key': name, 'reference_hash': row['reference_hash'], 'type': row['type']}
            for row in reference_rows for name in name_keys(row['reference'])]


def record(db, rows_):
    """Enregistre ces noms ; un nom déjà indexé pour la référence reste tel quel."""
    insert_new(db, AnalysisReferenceNameRow.__table__, rows_)


def search(db, scan_id, name, kind, after, limit):
    """Au plus `limit` références qui se retrouvent sous `name` (déjà comparable), après `after` : (nom,
    empreinte) de la dernière rendue. Rend aussi s'il en reste ; None si l'analyse n'a pas cet index."""
    named, reference = AnalysisReferenceNameRow, AnalysisReferenceRow
    statement = (select(named.name_key, named.reference_hash, reference.reference, named.type)
                 .join(reference, (reference.scan_id == named.scan_id)
                       & (reference.reference_hash == named.reference_hash))
                 .where(named.scan_id == scan_id, named.name_key == name))
    if kind is not None:
        statement = statement.where(named.type == kind)
    if after is not None:
        statement = statement.where(named.reference_hash > after[1])
    found = db.execute(statement.order_by(named.reference_hash).limit(limit + 1)).all()
    if not found and after is None and not indexed(db, scan_id):
        return None
    return found[:limit], len(found) > limit


def indexed(db, scan_id):
    """Vrai si les noms de l'analyse sont indexés, ou si elle ne nomme aucune référence."""
    named, reference = AnalysisReferenceNameRow, AnalysisReferenceRow
    return bool(db.scalar(select(exists().where(named.scan_id == scan_id)))
                or not db.scalar(select(exists().where(reference.scan_id == scan_id))))
