"""Reads of the versioned memory for comparing two analyses (TAXO-01F).

Every read is bound to one of the two analyses: walked by (scan_id, id), looked up on the other side
by (identity_hash, scan_id). The size of any other analysis never matters.
"""
import json

from sqlalchemy import and_, exists, false, or_, select
from sqlalchemy.orm import Session, aliased

from app.comparison.domain.comparison import Occurrence
from app.evaluations.domain.capability import LANGUAGE, WRITTEN_IN
from app.scans.infrastructure.sqlalchemy.fact_memory import (EVIDENCE_FIELDS, FactEvidenceRow, FactIdentityRow,
                                                             FactOccurrenceRow, ProducerExecutionRow,
                                                             SqlAlchemyFactMemory, _facts_of)

_CHUNK = 2000
_UNKNOWN = ('NOT_INTERPRETED', 'READ_ERROR')


class SqlAlchemyComparisonStore:
    def __init__(self, engine):
        self.engine = engine
        self.memory = SqlAlchemyFactMemory(engine)

    def producers(self, scan_id):
        found = {}
        with Session(self.engine) as db:
            for row in db.scalars(select(ProducerExecutionRow).where(ProducerExecutionRow.scan_id == scan_id)):
                found.setdefault(row.producer_id, []).append(row.execution())
            people = db.scalars(select(FactOccurrenceRow.human_producer_id).where(
                FactOccurrenceRow.scan_id == scan_id, FactOccurrenceRow.human_producer_id.is_not(None)).distinct())
            for person in people:
                found.setdefault(person, [])
        return found

    @staticmethod
    def _of(db, occurrence, scan_id, producer_id):
        """Occurrences of one producer in one analysis: its executions there, or the person itself."""
        executions = list(db.scalars(select(ProducerExecutionRow.id).where(
            ProducerExecutionRow.scan_id == scan_id, ProducerExecutionRow.producer_id == producer_id)))
        return and_(occurrence.scan_id == scan_id,
                    or_(occurrence.execution.in_(executions) if executions else false(),
                        occurrence.human_producer_id == producer_id))

    def _walk(self, db, scan_id, producer_id, *conditions, columns=()):
        """Facts (no coverage) of a producer in one analysis, chunk by chunk in occurrence order."""
        occurrence, last = FactOccurrenceRow, 0
        mine = self._of(db, occurrence, scan_id, producer_id)
        while True:
            rows = db.execute(
                select(occurrence.id, occurrence.identity_hash, *columns)
                .join(FactIdentityRow, FactIdentityRow.identity_hash == occurrence.identity_hash)
                .where(mine, occurrence.id > last, FactIdentityRow.kind != 'COVERAGE', *conditions)
                .order_by(occurrence.id).limit(_CHUNK)).all()
            if not rows:
                return
            yield rows
            last = rows[-1][0]

    def only(self, scan_id, other_id, producer_id):
        found = {}
        other = aliased(FactOccurrenceRow)
        identity = FactIdentityRow
        with Session(self.engine) as db:
            theirs = self._of(db, other, other_id, producer_id)
            absent = ~exists().where(other.identity_hash == FactOccurrenceRow.identity_hash, theirs)
            for rows in self._walk(db, scan_id, producer_id, absent,
                                   columns=(identity.kind, identity.subject, identity.relation)):
                for _, identity_hash, kind, subject, relation in rows:
                    found[identity_hash] = (kind, subject, relation) if kind == 'ASSERTION' else None
        return found

    @staticmethod
    def _occurrences(db, condition, identity_hashes):
        occurrence = FactOccurrenceRow
        rows = db.execute(select(occurrence.id, occurrence.identity_hash, occurrence.status, occurrence.validity,
                                 occurrence.has_evidence, occurrence.details, occurrence.raw_identity)
                          .where(condition, occurrence.identity_hash.in_(identity_hashes))
                          .order_by(occurrence.id)).all()
        evidence = {}
        ids = [row.id for row in rows if row.has_evidence]
        for start in range(0, len(ids), 500):
            for item in db.scalars(select(FactEvidenceRow).where(FactEvidenceRow.occurrence.in_(ids[start:start + 500]))
                                   .order_by(FactEvidenceRow.occurrence, FactEvidenceRow.position)):
                evidence.setdefault(item.occurrence, []).append(tuple(getattr(item, name) for name in EVIDENCE_FIELDS))
        found = {}
        for row in rows:
            proofs = tuple(evidence.get(row.id, ())) if row.has_evidence else None
            content = json.dumps([row.details, row.raw_identity], sort_keys=True, ensure_ascii=False)
            found.setdefault(row.identity_hash, []).append(Occurrence(row.id, row.status, row.validity, proofs, content))
        return found

    def common(self, before_id, after_id, producer_id):
        seen = set()
        with Session(self.engine) as db:
            after = aliased(FactOccurrenceRow)
            theirs = self._of(db, after, after_id, producer_id)
            shared = exists().where(after.identity_hash == FactOccurrenceRow.identity_hash, theirs)
            mine = self._of(db, FactOccurrenceRow, before_id, producer_id)
            others = self._of(db, FactOccurrenceRow, after_id, producer_id)
            for rows in self._walk(db, before_id, producer_id, shared):
                hashes = sorted({identity_hash for _, identity_hash in rows} - seen)
                seen.update(hashes)
                left, right = self._occurrences(db, mine, hashes), self._occurrences(db, others, hashes)
                for identity_hash in hashes:
                    yield identity_hash, left[identity_hash], right[identity_hash]

    def commit(self, scan_id, sha):
        """Read through the `commit:` reference index of the analysis: two lookups, never a walk."""
        reference = f'commit:{sha}'
        recorded = self.memory.neighbor(scan_id, reference, 'HAS_COMMIT', 'INCOMING')
        if recorded is None:
            return None
        qualifiers = recorded[1].get('qualifiers') or {}
        author, named = self.memory.neighbor(scan_id, reference, 'AUTHORED_BY', 'OUTGOING'), None
        if author is not None:
            named = (author[1].get('qualifiers') or {}).get('name') or author[1]['object'].removeprefix('person:')
        return {'sha': sha, 'subject': qualifiers.get('subject'), 'authored_at': qualifiers.get('authored_at'),
                'committed_at': qualifiers.get('committed_at'), 'author': named}

    def labels(self, identity_hashes):
        found = {}
        identity = FactIdentityRow
        with Session(self.engine) as db:
            for start in range(0, len(identity_hashes), 500):
                rows = db.execute(select(identity.identity_hash, identity.kind, identity.relation)
                                  .where(identity.identity_hash.in_(identity_hashes[start:start + 500]))).all()
                found |= {identity_hash: relation if kind == 'ASSERTION' and relation else kind
                          for identity_hash, kind, relation in rows}
        return found

    def languages(self, scan_id):
        return tuple(value[len(LANGUAGE):] for value in self.memory.objects(scan_id, WRITTEN_IN)
                     if value and value.startswith(LANGUAGE))

    def unknown(self, scan_id):
        identity = FactIdentityRow
        with Session(self.engine) as db:
            rows = db.execute(select(FactOccurrenceRow.identity_hash, identity.identity)
                              .join(identity, identity.identity_hash == FactOccurrenceRow.identity_hash)
                              .where(FactOccurrenceRow.scan_id == scan_id, identity.kind == 'COVERAGE')).all()
        return len({identity_hash for identity_hash, value in rows if value.get('coverage_type') in _UNKNOWN})

    def facts(self, scan_id, producer_id, identity_hashes):
        found = {}
        with Session(self.engine) as db:
            mine = self._of(db, FactOccurrenceRow, scan_id, producer_id)
            for start in range(0, len(identity_hashes), 500):
                chunk = identity_hashes[start:start + 500]
                statement = (_facts_of(scan_id).where(mine, FactOccurrenceRow.identity_hash.in_(chunk))
                             .order_by(FactOccurrenceRow.id))
                for row, fact in self.memory.load_rows(db, scan_id, statement):
                    found.setdefault(row[0].identity_hash, []).append(fact)
        return found
