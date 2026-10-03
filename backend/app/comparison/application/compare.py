"""Compare two analyses of a project from the versioned memory (TAXO-01F).

No repository is read and no evaluator runs: only the recorded identities and occurrences of the two
analyses are read. Counts first; each category then lists its facts, page by page.
"""
import threading
from collections import OrderedDict

from app.comparison.application.analyses import described
from app.comparison.domain.comparison import (ADDED, CATEGORIES, MODIFIED, REASONS, REMOVED, Side,
                                              comparability, pair_modified, signals)
from app.evaluations.domain.capability import CatalogContracts, Reads, languages_complete
from app.knowledge.application.loader import recorded_languages
from app.knowledge.domain.knowledge import AnalysisKnowledge
from app.projects.application.queries import require_project
from app.projects.domain.project import ProjectError

UNCHANGED = 'UNCHANGED'
LABELS = 'LABELS'
MAX_PAGE = 200
# A complete analysis never changes again: a computed comparison stays true. Only the identities of the
# differences are kept (never whole analyses), for the few comparisons being browsed.
KEPT_COMPARISONS = 8


def _side(executions, statuses, reads, knowledge):
    """`reads` : ce que lit le contrat de ces executions ; `knowledge` : ce que l'analyse sait d'elle-meme. Une
    absence de langage ne se deduit que d'un inventaire complet, et d'un contrat connu."""
    if executions is None:
        return None
    return Side(frozenset((item.catalog_id, item.catalog_version) for item in executions),
                frozenset(item.producer_version for item in executions),
                any(statuses.get(item.execution_id) == 'FAILED' for item in executions),
                not any(statuses.get(item.execution_id) == 'UNSUPPORTED' for item in executions)
                and (not knowledge.complete or reads.reads_present(knowledge.languages)), reads.known)


def _statuses(scan):
    return {item.get('execution_id'): item.get('status') for item in scan.result.get('evaluations', [])}


class CompareAnalyses:
    def __init__(self, projects, scans, store, contracts=None):
        self.projects, self.scans, self.store = projects, scans, store
        # Ce que lit chaque contrat de catalogue (TAXO-COV-01) ; sans contrats, aucune regle de langage.
        self.contracts = contracts or CatalogContracts()
        self._kept, self._lock = OrderedDict(), threading.Lock()

    def _analyses(self, project_id, before_id, after_id):
        require_project(self.projects, project_id)
        found = [self.scans.get(project_id, scan_id) for scan_id in (before_id, after_id)]
        if any(scan is None for scan in found):
            raise ProjectError('NOT_FOUND', 'Analyse introuvable pour ce projet, ou interrompue.')
        return found

    def _knowledge(self, scan):
        """Ce que l'analyse sait d'elle-meme pour etre comparee : ses langages (enregistres avec elle, ou relus
        dans ses faits si elle est anterieure) et si son inventaire a tout lu."""
        recorded = recorded_languages(scan)
        languages = recorded if recorded is not None else self.store.languages(scan.id)
        return AnalysisKnowledge(languages, languages_complete(scan.result.get('evaluation_summary')))

    def _read(self, executions):
        """Ce que lit le contrat de ces executions. Un contrat que ce Taxo ne connait pas ne lit rien de connu,
        comme pour les verdicts. Seul un evaluateur nomme un catalogue : une projection n'en a pas, et n'est
        liee a aucun contrat. Plusieurs executions d'un producteur suivent la regle commune (`Reads.combined`) :
        leur contrat commun, sinon inconnu. Sans contrats fournis, aucune regle de langage ne s'applique."""
        if not self.contracts:
            return Reads.any()
        return Reads.combined([self.contracts.reads(item.catalog_id, item.catalog_version)
                               for item in executions or () if item.producer_type == 'EVALUATOR'], Reads.any())

    def _producers(self, before, after, unread=None):
        """Chaque producteur et ce que dit de lui chaque cote. `unread`, s'il est donne, recoit pour chaque
        producteur les langages presents de chaque cote que son catalogue ne lit pas."""
        sides = [(scan, self.store.producers(scan.id), self._knowledge(scan)) for scan in (before, after)]
        names = sorted({name for _, found, _ in sides for name in found})
        if unread is not None:
            unread.update({name: {side: self._unread(found.get(name), knowledge.languages)
                                  for side, (_, found, knowledge) in zip(('before', 'after'), sides)}
                           for name in names})
        return {name: [_side(found.get(name), _statuses(scan), self._read(found.get(name)), knowledge)
                       for scan, found, knowledge in sides]
                for name in names}

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
        unread = {}
        producers = self._producers(before, after, unread)
        evaluators = [self._evaluator(before, after, producer, sides, unread[producer])
                      for producer, sides in producers.items()]
        totals = dict.fromkeys((*CATEGORIES, UNCHANGED), 0)
        for entry in evaluators:
            for name, count in entry.get('counts', {}).items():
                totals[name] += count
        return {'before': described(before), 'after': described(after), 'evaluators': evaluators, 'totals': totals,
                'unknown': {'before': self.store.unknown(before.id), 'after': self.store.unknown(after.id)}}

    def _evaluator(self, before, after, producer, sides, not_analysed):
        """Ce que la comparaison dit d'un evaluateur : comparable, avec ses comptes, ou pourquoi il ne l'est pas."""
        left, right = sides
        reason = comparability(left, right)
        entry = {'evaluator_id': producer, 'comparable': reason is None,
                 'versions': {'before': sorted(left.versions) if left else [],
                              'after': sorted(right.versions) if right else []},
                 'not_analysed': not_analysed}
        if reason is not None:
            return entry | {'reason': reason, 'message': REASONS[reason]}
        found = self._compute(before, after, producer)
        entry['counts'] = {name: found[name] if name == UNCHANGED else len(found[name])
                           for name in (*CATEGORIES, UNCHANGED)}
        entry['relations'] = _relations(found)
        return entry

    def changes(self, project_id, before_id, after_id, category, producer, cursor=None, limit=50, relation=None):
        if category not in CATEGORIES:
            raise ProjectError('INVALID_ARGUMENT', f'Catégorie inconnue : {category}.')
        before, after = self._analyses(project_id, before_id, after_id)
        left, right = self._producers(before, after).get(producer, (None, None))
        reason = comparability(left, right)
        if reason is not None:
            raise ProjectError('INVALID_ARGUMENT', f'{producer} : {REASONS[reason]}')
        page, more = _page(self._compute(before, after, producer), category, relation, cursor, limit)
        facts_before = self._facts(before, producer, [old for old, _ in page] if category != ADDED else [])
        facts_after = self._facts(after, producer, [new for _, new in page] if category != REMOVED else [])
        items = [{'before': facts_before.get(old, []), 'after': facts_after.get(new, [])} for old, new in page]
        return {'category': category, 'evaluator_id': producer, 'relation': relation, 'items': items,
                'next': page[-1][0] if more else None}

    def facts_changed(self, before, after, producers):
        """Pour l'impact d'un commit (TAXO-01F, tranche E), par producteur : la raison qui empeche de le comparer,
        sinon les faits de chaque cote dont l'identite n'est pas de l'autre cote, le nombre d'identites communes et
        les zones que chaque cote n'a pas interpretees. Les signaux d'une identite commune (preuve, statut,
        occurrences) n'en font pas partie : l'impact compte ces faits inchanges."""
        sides = self._producers(before, after)
        found = {}
        for producer in producers:
            reason = comparability(*sides.get(producer, (None, None)))
            # Ne pas comparer les faits ne fait pas oublier ce que chaque cote n'a pas interprete.
            unread = {'before': self.store.unread(before.id, producer), 'after': self.store.unread(after.id, producer)}
            if reason is not None:
                found[producer] = {'reason': reason, 'message': REASONS[reason], 'unread': unread}
                continue
            changed = self._compute(before, after, producer)
            removed = changed[REMOVED] + [old for old, _ in changed[MODIFIED]]
            added = changed[ADDED] + [new for _, new in changed[MODIFIED]]
            found[producer] = {'reason': None, 'unchanged': changed[UNCHANGED], 'unread': unread,
                               'before': _flat(self._facts(before, producer, removed)),
                               'after': _flat(self._facts(after, producer, added))}
        return found

    def _facts(self, scan, producer, identity_hashes):
        return self.store.facts(scan.id, producer, identity_hashes) if identity_hashes else {}


def _flat(found):
    """Les faits rebatis, chaque identite dans l'ordre de ses occurrences."""
    return [fact for identity_hash in sorted(found) for fact in found[identity_hash]]


def _page(found, category, relation, cursor, limit):
    """Une page des differences d'une categorie, eventuellement d'une seule relation, apres `cursor` ; et s'il
    en reste ensuite."""
    pairs = [_pair(category, entry) for entry in found[category]
             if relation is None or found[LABELS].get(_pair(category, entry)[0]) == relation]
    remaining = [pair for pair in pairs if cursor is None or pair[0] > cursor]
    page = remaining[:max(1, min(limit, MAX_PAGE))]
    return page, len(remaining) > len(page)


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
