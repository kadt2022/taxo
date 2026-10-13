from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.evaluations.domain.evaluator import EvaluatorCatalog
from app.evaluations.domain.status import EvaluationStatus
from app.facts.domain.provenance import ProducerExecution
from app.snapshots.domain.snapshot import Snapshot

# Le resume reste borne : les premiers avertissements suffisent a expliquer un statut partiel ou en echec.
SUMMARY_WARNINGS = 5


@dataclass(frozen=True)
class EvaluatorExecution:
    execution_id: str
    evaluator_id: str
    producer_version: str
    catalog: EvaluatorCatalog
    snapshot: Snapshot
    started_at: datetime
    finished_at: datetime
    scope: dict
    status: EvaluationStatus
    facts: tuple[dict[str, Any], ...] = ()
    coverage: tuple[dict[str, Any], ...] = ()
    warnings: tuple[str, ...] = ()
    legacy: dict[str, Any] | None = None

    def __post_init__(self):
        if not self.coverage:
            raise ValueError("Une exécution d'évaluateur doit déclarer sa couverture.")

    def producer_execution(self):
        """What the fact memory records before accepting this execution's facts."""
        return ProducerExecution('EVALUATOR', self.evaluator_id, self.producer_version, self.execution_id,
                                 self.catalog.catalog_id, self.catalog.catalog_version)

    def restitution(self):
        """Ce que l'analyseur a restitué de ce qu'il a lu (objectif : 1 % au plus de non restitué). Un site d'appel est
        restitué s'il prouve un fait (`role: call-site`), non restitué s'il n'est que dans un diagnostic de couverture ;
        un sujet non lu est une couverture illisible, ou non interprétée sans site."""
        restituted = sum(1 for fact in self.facts for proof in fact.get('evidence', ())
                         if proof.get('role') == 'call-site')
        kept = [((fact.get('diagnostic') or {}).get('sites') or ()) for fact in self.coverage
                if fact['coverage_type'] == 'NOT_INTERPRETED']
        unread = sum(1 for fact in self.coverage if fact['coverage_type'] == 'READ_ERROR'
                     or (fact['coverage_type'] == 'NOT_INTERPRETED' and not (fact.get('diagnostic') or {}).get('sites')))
        return {'sites_restituted': restituted, 'sites_not_restituted': sum(len(sites) for sites in kept),
                'subjects_not_read': unread}

    def summary(self):
        coverage_counts = Counter()
        coverage_subjects = {}
        for fact in self.coverage:
            coverage_type = fact['coverage_type']
            coverage_counts[coverage_type] += 1
            subjects = coverage_subjects.setdefault(coverage_type, [])
            if len(subjects) < 5 and fact['subject'] not in subjects:
                subjects.append(fact['subject'])
        relations = Counter(
            fact['relation'] for fact in self.facts
            if fact.get('kind') == 'ASSERTION' and 'relation' in fact
        )
        return {
            'execution_id': self.execution_id,
            'evaluator_id': self.evaluator_id,
            'producer_version': self.producer_version,
            'catalog_id': self.catalog.catalog_id,
            'catalog_version': self.catalog.catalog_version,
            'status': self.status.value,
            'started_at': self.started_at.isoformat(),
            'finished_at': self.finished_at.isoformat(),
            'duration_seconds': round((self.finished_at - self.started_at).total_seconds(), 3),
            'fact_count': len(self.facts),
            'coverage_count': len(self.coverage),
            'warning_count': len(self.warnings),
            'warnings': list(dict.fromkeys(self.warnings))[:SUMMARY_WARNINGS],
            'relations': dict(sorted(relations.items())),
            'restitution': self.restitution(),
            'coverage': [
                {'coverage_type': kind, 'count': coverage_counts[kind], 'subjects': coverage_subjects[kind]}
                for kind in sorted(coverage_counts)
            ],
            'snapshot': self.snapshot.reference(),
        }

    def result(self):
        return {
            'execution_id': self.execution_id,
            'evaluator_id': self.evaluator_id,
            'producer_version': self.producer_version,
            'catalog_id': self.catalog.catalog_id,
            'catalog_version': self.catalog.catalog_version,
            'started_at': self.started_at.isoformat(),
            'finished_at': self.finished_at.isoformat(),
            'scope': self.scope,
            'status': self.status.value,
            'facts': list(self.facts),
            'coverage': list(self.coverage),
            'warnings': list(self.warnings),
        }
