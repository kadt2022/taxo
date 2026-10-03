"""Les références présentes dans une analyse, cherchées par préfixe (TAXO-01J, `find_references`).

Une projection de la mémoire : une ligne par référence nommée par une assertion de l'analyse (sujet, ou objet
quand c'est une référence), dans l'orthographe soumise (celle que le parcours accepte comme ancre), écrite
dans la même transaction que ses faits. La recherche est une lecture par
plage d'un index B-tree de taille fixe, bornée par la page demandée : jamais un parcours des faits.

La clé de recherche suit la règle du domaine (`app.neighborhood.domain.references.fold`). L'ordre est celui
de la clé, puis de l'empreinte de la référence.
"""
import hashlib

from sqlalchemy import Column, ForeignKey, Index, String, Text, select
from sqlalchemy.dialects import postgresql, sqlite

from app.neighborhood.domain.references import KEY_LENGTH, fold
from app.platform.database.base import Base


def _ordered(length):
    """Un ordre d'octets, le même partout : sans lui, PostgreSQL comparerait selon la langue de la base."""
    return String(length).with_variant(postgresql.VARCHAR(length, collation='C'), 'postgresql')


class AnalysisReferenceRow(Base):
    __tablename__ = 'analysis_references'
    scan_id = Column(String, ForeignKey('scans.id'), primary_key=True)
    reference_hash = Column(_ordered(64), primary_key=True)
    search_key = Column(_ordered(KEY_LENGTH), nullable=False)
    type = Column(String, nullable=False)
    reference = Column(Text, nullable=False)
    __table_args__ = (Index('ix_analysis_references_key', 'scan_id', 'search_key', 'reference_hash'),
                      Index('ix_analysis_references_type', 'scan_id', 'type', 'search_key', 'reference_hash'))


def search_key(text):
    """La règle du domaine (`fold`), sans rien y ajouter."""
    return fold(text)


def successor(prefix):
    """La plus petite chaîne plus grande que toutes celles qui commencent par `prefix`, dans l'ordre des points
    de code (celui des octets UTF-8) ; None s'il n'y en a pas."""
    while prefix:
        last = ord(prefix[-1])
        if last < 0x10FFFF:
            following = last + 1 if last + 1 not in range(0xD800, 0xE000) else 0xE000
            return prefix[:-1] + chr(following)
        prefix = prefix[:-1]
    return None


def reference_hash(reference):
    return hashlib.sha256(reference.encode()).hexdigest()


def rows(scan_id, references):
    """Les lignes à enregistrer pour ces références d'une analyse, dans l'orthographe soumise."""
    found = {}
    for reference in references:
        kind, _, key = reference.partition(':')
        found[reference_hash(reference)] = {'scan_id': scan_id, 'reference_hash': reference_hash(reference),
                                            'search_key': search_key(key), 'type': kind, 'reference': reference}
    return list(found.values())


def record(db, rows_):
    """Enregistre ces lignes ; une référence déjà indexée pour l'analyse reste telle quelle."""
    if not rows_:
        return
    dialect = postgresql if db.get_bind().dialect.name == 'postgresql' else sqlite
    table = AnalysisReferenceRow.__table__
    for start in range(0, len(rows_), 500):
        db.execute(dialect.insert(table).on_conflict_do_nothing(index_elements=['scan_id', 'reference_hash']),
                   rows_[start:start + 500])


def search(db, scan_id, prefix, kind, after, limit):
    """Au plus `limit` références dont la clé commence par `prefix` (déjà repliée), après `after` : (clé,
    empreinte) de la dernière rendue. Rend aussi s'il en reste."""
    row = AnalysisReferenceRow
    statement = select(row.search_key, row.reference_hash, row.reference, row.type).where(row.scan_id == scan_id)
    if kind is not None:
        statement = statement.where(row.type == kind)
    if prefix:
        # La plage exacte des clés qui commencent par le préfixe, dans l'ordre des octets.
        statement = statement.where(row.search_key >= prefix)
        upper = successor(prefix)
        if upper is not None:
            statement = statement.where(row.search_key < upper)
    if after is not None:
        statement = statement.where((row.search_key > after[0])
                                    | ((row.search_key == after[0]) & (row.reference_hash > after[1])))
    found = db.execute(statement.order_by(row.search_key, row.reference_hash).limit(limit + 1)).all()
    return found[:limit], len(found) > limit
