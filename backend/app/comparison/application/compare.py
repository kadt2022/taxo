"""Compare two analyses of a project from the versioned memory (TAXO-01F).

No repository is read and no evaluator runs: only the recorded identities and occurrences of the two
analyses are read. Counts first; each category then lists its facts, page by page.
"""
import threading
from collections import OrderedDict

from app.comparison.domain.comparison import (ADDED, CATEGORIES, MODIFIED, REASONS, REMOVED, Side,
                                              comparability, pair_modified, signals)
from app.evaluations.domain.capability import CatalogContracts, Reads, languages_complete
from app.projects.application.queries import require_project
from app.projects.domain.project import ProjectError

UNCHANGED = 'UNCHANGED'
LABELS = 'LABELS'
MAX_PAGE = 200
# A complete analysis never changes again: a computed comparison stays true. Only the identities of the
# differences are kept (never whole analyses), for the few comparisons being browsed.
KEPT_COMPARISONS = 8


def _side(executions, statuses, reads, present, complete=True):
    """`reads` : ce que lit le contrat de ces executions. Une absence de langage ne se deduit que d'un
    inventaire `complete`, et d'un contrat connu."""
    if executions is None:
        return None
    return Side(frozenset((item.catalog_id, item.catalog_version) for item in executions),
                frozenset(item.producer_version for item in executions),
                any(statuses.get(item.execution_id) == 'FAILED' for item in executions),
                not any(statuses.get(item.execution_id) == 'UNSUPPORTED' for item in executions)
                and (not complete or reads.reads_present(present)), reads.known)


def _statuses(scan):
    return {item.get('execution_id'): item.get('status') for item in scan.result.get('evaluations', [])}


def _snapshot(scan):
    return (scan.result.get('evaluation_summary') or {}).get('snapshot') or scan.result.get('snapshot')


def _describe(scan):
    return {'id': scan.id, 'created_at': scan.created_at, 'snapshot': _snapshot(scan)}


class CompareAnalyses:
    def __init__(self, projects, scans, store, contracts=None):
        self.projects, self.scans, self.store = projects, scans, store
        # Ce que lit chaque contrat de catalogue (TAXO-COV-01) ; sans contrats, aucune regle de langage.
        self.contracts = contracts or CatalogContracts()
        self._kept, self._lock = OrderedDict(), threading.Lock()

    def choices(self, project_id):
        """The complete analyses of the project, newest first, each described enough to be recognised.

        The commit is described from the analysis's own Git facts, never by reading the repository again.
        """
        require_project(self.projects, project_id)
        return [self._choice(scan) for scan in self.scans.list(project_id)]

    def _choice(self, scan):
        sha = (_snapshot(scan) or {}).get('commit')
        evaluations = scan.result.get('evaluations', [])
        return {**_describe(scan), 'commit': self.store.commit(scan.id, sha) if sha else None,
                'fact_count': sum(item.get('fact_count') or 0 for item in evaluations),
                'failed': sorted(item.get('evaluator_id') for item in evaluations if item.get('status') == 'FAILED')}

    def _analyses(self, project_id, before_id, after_id):
        require_project(self.projects, project_id)
        found = [self.scans.get(project_id, scan_id) for scan_id in (before_id, after_id)]
        if any(scan is None for scan in found):
            raise ProjectError('NOT_FOUND', 'Analyse introuvable pour ce projet, ou interrompue.')
        return found

    def _languages(self, scan):
        """Les langages de l'analyse : enregistres avec elle, ou relus dans ses faits si elle est anterieure."""
        recorded = scan.result.get('languages')
        return tuple(recorded) if recorded is not None else self.store.languages(scan.id)

    def _read(self, executions):
        """Ce que lit le contrat de ces executions. Un contrat que ce Taxo ne connait pas ne lit rien de connu,
        comme pour les verdicts. Seul un evaluateur nomme un catalogue : une projection n'en a pas, et n'est
        liee a aucun contrat. Plusieurs contrats lies a des langages lisent leur union. Sans contrats fournis,
        aucune regle de langage ne s'applique."""
        if not self.contracts:
            return Reads.any()
        found = [self.contracts.reads(item.catalog_id, item.catalog_version) for item in executions or ()
                 if item.producer_type == 'EVALUATOR']
        if not all(item.known for item in found):
            return Reads.unknown()
        declared = [item.languages for item in found if not item.independent]
        return Reads.declared(frozenset().union(*declared)) if declared else Reads.any()

    def _producers(self, before, after, unread=None):
        """Chaque producteur et ce que dit de lui chaque cote. `unread`, s'il est donne, recoit pour chaque
        producteur les langages presents de chaque cote que son catalogue ne lit pas."""
        sides = [(scan, self.store.producers(scan.id), self._languages(scan)) for scan in (before, after)]
        names = sorted({name for _, found, _ in sides for name in found})
        if unread is not None:
            unread.update({name: {side: self._unread(found.get(name), present)
                                  for side, (_, found, present) in zip(('before', 'after'), sides)}
                           for name in names})
        return {name: [self._side_of(scan, found.get(name), present) for scan, found, present in sides]
                for name in names}

    def _side_of(self, scan, executions, present):
        return _side(executions, _statuses(scan), self._read(executions), present,
                     languages_complete(scan.result.get('evaluation_summary')))

    def _unread(self, executions, present):
        """Les langages presents que le catalogue de ces executions ne lit pas (TAXO-COV-01)."""
        return list(self._read(executions).unread(present))

    def _compute(self, before, after, producer):
        key = (before.id, after.id, producer)
        with self._lock:
            if key in self._kept:
                self._kept.move_to_end(key)
                return self._kept[key]
        found = self._differences(before, after, producer)
        with self._lock:
            self._kept[key] = found
            while len(self._kept) > KEPT_COMPARISONS:
                self._kept.popitem(last=False)
        return found

    def _differences(self, before, after, producer):
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
        # What each difference is about (its relation), read by identity: the domains group these counts.
        keys = {_pair(name, entry)[0] for name in CATEGORIES for entry in found[name]}
        found[LABELS] = self.store.labels(sorted(keys))
        return found

    def summary(self, project_id, before_id, after_id):
        before, after = self._analyses(project_id, before_id, after_id)
        evaluators, totals = [], dict.fromkeys((*CATEGORIES, UNCHANGED), 0)
        unread = {}
        for producer, (left, right) in self._producers(before, after, unread).items():
            reason = comparability(left, right)
            entry = {'evaluator_id': producer, 'comparable': reason is None,
                     'versions': {'before': sorted(left.versions) if left else [],
                                  'after': sorted(right.versions) if right else []},
                     'not_analysed': unread[producer]}
            if reason is not None:
                entry |= {'reason': reason, 'message': REASONS[reason]}
            else:
                found = self._compute(before, after, producer)
                entry['counts'] = {name: found[name] if name == UNCHANGED else len(found[name])
                                   for name in (*CATEGORIES, UNCHANGED)}
                for name, count in entry['counts'].items():
                    totals[name] += count
                entry['relations'] = _relations(found)
            evaluators.append(entry)
        return {'before': _describe(before), 'after': _describe(after), 'evaluators': evaluators, 'totals': totals,
                'unknown': {'before': self.store.unknown(before.id), 'after': self.store.unknown(after.id)}}

    def changes(self, project_id, before_id, after_id, category, producer, cursor=None, limit=50, relation=None):
        if category not in CATEGORIES:
            raise ProjectError('INVALID_ARGUMENT', f'Catégorie inconnue : {category}.')
        before, after = self._analyses(project_id, before_id, after_id)
        left, right = self._producers(before, after).get(producer, (None, None))
        reason = comparability(left, right)
        if reason is not None:
            raise ProjectError('INVALID_ARGUMENT', f'{producer} : {REASONS[reason]}')
        found = self._compute(before, after, producer)
        pairs = [_pair(category, entry) for entry in found[category]
                 if relation is None or found[LABELS].get(_pair(category, entry)[0]) == relation]
        remaining = [pair for pair in pairs if cursor is None or pair[0] > cursor]
        page = remaining[:max(1, min(limit, MAX_PAGE))]
        facts_before = self._facts(before, producer, [old for old, _ in page] if category != ADDED else [])
        facts_after = self._facts(after, producer, [new for _, new in page] if category != REMOVED else [])
        items = [{'before': facts_before.get(old, []), 'after': facts_after.get(new, [])} for old, new in page]
        more = len(remaining) > len(page)
        return {'category': category, 'evaluator_id': producer, 'relation': relation, 'items': items,
                'next': page[-1][0] if more else None}

    def _facts(self, scan, producer, identity_hashes):
        return self.store.facts(scan.id, producer, identity_hashes) if identity_hashes else {}


def _pair(category, entry):
    """(before identity, after identity) of a listed entry; the before side keys the page."""
    return tuple(entry) if category == MODIFIED else (entry, entry)


def _relations(found):
    """Counts of each category by relation (or kind): {relation: {category: count}}, zeros left out."""
    counts = {}
    for name in CATEGORIES:
        for entry in found[name]:
            label = found[LABELS].get(_pair(name, entry)[0], 'UNKNOWN')
            counts.setdefault(label, dict.fromkeys(CATEGORIES, 0))[name] += 1
    return {label: {name: count for name, count in value.items() if count} for label, value in sorted(counts.items())}
