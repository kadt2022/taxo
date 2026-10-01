"""Compare two analyses of a project from the versioned memory (TAXO-01F).

No repository is read and no evaluator runs: only the recorded identities and occurrences of the two
analyses are read. Counts first; each category then lists its facts, page by page.
"""
from app.comparison.domain.comparison import (ADDED, CATEGORIES, MODIFIED, REASONS, REMOVED, Side,
                                              comparability, pair_modified, signals)
from app.projects.application.queries import require_project
from app.projects.domain.project import ProjectError

UNCHANGED = 'UNCHANGED'
MAX_PAGE = 200


def _side(executions, statuses):
    if executions is None:
        return None
    return Side(frozenset((item.catalog_id, item.catalog_version) for item in executions),
                frozenset(item.producer_version for item in executions),
                any(statuses.get(item.execution_id) == 'FAILED' for item in executions))


def _statuses(scan):
    return {item.get('execution_id'): item.get('status') for item in scan.result.get('evaluations', [])}


def _describe(scan):
    snapshot = (scan.result.get('evaluation_summary') or {}).get('snapshot') or scan.result.get('snapshot')
    return {'id': scan.id, 'created_at': scan.created_at, 'snapshot': snapshot}


class CompareAnalyses:
    def __init__(self, projects, scans, store):
        self.projects, self.scans, self.store = projects, scans, store

    def _analyses(self, project_id, before_id, after_id):
        require_project(self.projects, project_id)
        found = [self.scans.get(project_id, scan_id) for scan_id in (before_id, after_id)]
        if any(scan is None for scan in found):
            raise ProjectError('NOT_FOUND', 'Analyse introuvable pour ce projet, ou interrompue.')
        return found

    def _producers(self, before, after):
        producers = {}
        sides = ((before, self.store.producers(before.id)), (after, self.store.producers(after.id)))
        for name in sorted({name for _, found in sides for name in found}):
            versions = [_side(found.get(name), _statuses(scan)) for scan, found in sides]
            producers[name] = versions
        return producers

    def _compute(self, before, after, producer):
        removed = self.store.only(before.id, after.id, producer)
        added = self.store.only(after.id, before.id, producer)
        removed, added, modified = pair_modified(removed, added)
        found = {ADDED: added, REMOVED: removed, MODIFIED: modified, UNCHANGED: 0}
        for name in CATEGORIES:
            found.setdefault(name, [])
        for identity_hash, left, right in self.store.common(before.id, after.id, producer):
            found[UNCHANGED] += 1
            for signal in signals(left, right):
                found[signal].append(identity_hash)
        for name in CATEGORIES:
            found[name].sort()
        return found

    def summary(self, project_id, before_id, after_id):
        before, after = self._analyses(project_id, before_id, after_id)
        evaluators, totals = [], dict.fromkeys((*CATEGORIES, UNCHANGED), 0)
        for producer, (left, right) in self._producers(before, after).items():
            reason = comparability(left, right)
            entry = {'evaluator_id': producer, 'comparable': reason is None,
                     'versions': {'before': sorted(left.versions) if left else [],
                                  'after': sorted(right.versions) if right else []}}
            if reason is not None:
                entry |= {'reason': reason, 'message': REASONS[reason]}
            else:
                found = self._compute(before, after, producer)
                entry['counts'] = {name: found[name] if name == UNCHANGED else len(found[name])
                                   for name in (*CATEGORIES, UNCHANGED)}
                for name, count in entry['counts'].items():
                    totals[name] += count
            evaluators.append(entry)
        return {'before': _describe(before), 'after': _describe(after), 'evaluators': evaluators, 'totals': totals,
                'unknown': {'before': self.store.unknown(before.id), 'after': self.store.unknown(after.id)}}

    def changes(self, project_id, before_id, after_id, category, producer, cursor=None, limit=50):
        if category not in CATEGORIES:
            raise ProjectError('INVALID_ARGUMENT', f'Catégorie inconnue : {category}.')
        before, after = self._analyses(project_id, before_id, after_id)
        left, right = self._producers(before, after).get(producer, (None, None))
        reason = comparability(left, right)
        if reason is not None:
            raise ProjectError('INVALID_ARGUMENT', f'{producer} : {REASONS[reason]}')
        pairs = [_pair(category, entry) for entry in self._compute(before, after, producer)[category]]
        remaining = [pair for pair in pairs if cursor is None or pair[0] > cursor]
        page = remaining[:max(1, min(limit, MAX_PAGE))]
        facts_before = self._facts(before, producer, [old for old, _ in page] if category != ADDED else [])
        facts_after = self._facts(after, producer, [new for _, new in page] if category != REMOVED else [])
        items = [{'before': facts_before.get(old, []), 'after': facts_after.get(new, [])} for old, new in page]
        more = len(remaining) > len(page)
        return {'category': category, 'evaluator_id': producer, 'items': items,
                'next': page[-1][0] if more else None}

    def _facts(self, scan, producer, identity_hashes):
        return self.store.facts(scan.id, producer, identity_hashes) if identity_hashes else {}


def _pair(category, entry):
    """(before identity, after identity) of a listed entry; the before side keys the page."""
    return tuple(entry) if category == MODIFIED else (entry, entry)
