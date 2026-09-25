"""Projection des faits Git selon la requete (TAXO-QUERY-01) : la selection vient apres l'analyse.

L'evaluateur Git a observe tout l'historique ; la projection choisit, parmi ces faits conserves, ceux que
la requete vise. Les faits sont rendus tels quels : provenance, preuves et qualificatifs compris.

L'ordre des commits est celui de `git log --date-order`, reconstruit a partir des faits : un commit vient
toujours avant ses parents (CHILD_OF), et parmi les commits disponibles le plus recent d'abord.
"""
import heapq
from collections import defaultdict
from datetime import datetime

from .request import COMMIT, LATEST, PERIOD

SELECTED, NOT_FOUND, AMBIGUOUS = 'SELECTED', 'NOT_FOUND', 'AMBIGUOUS'
_PREFIX = 'commit:'


def _sha(reference):
    return reference[len(_PREFIX):]


def _moment(value):
    try:
        return datetime.fromisoformat(value).timestamp()
    except (TypeError, ValueError):
        return 0.0


def _index(facts):
    commits, attached, parents = {}, defaultdict(list), defaultdict(list)
    for fact in facts:
        if fact.get('kind') != 'ASSERTION':
            continue
        if fact['relation'] == 'HAS_COMMIT':
            sha = _sha(fact['object'])
            commits[sha] = {'sha': sha, **fact.get('qualifiers', {})}
            attached[sha].insert(0, fact)
        elif fact['subject'].startswith(_PREFIX):
            attached[_sha(fact['subject'])].append(fact)
            if fact['relation'] == 'CHILD_OF':
                parents[_sha(fact['subject'])].append(_sha(fact['object']))
    return commits, attached, parents


def log_order(commits, parents):
    """Enfants avant parents ; a egalite, date d'auteur la plus recente, puis identifiant."""
    children = defaultdict(int)
    for sha in commits:
        for parent in parents[sha]:
            if parent in commits:
                children[parent] += 1
    ready = [(-_moment(commits[sha].get('authored_at')), sha) for sha in commits if not children[sha]]
    heapq.heapify(ready)
    order = []
    while ready:
        _, sha = heapq.heappop(ready)
        order.append(sha)
        for parent in parents[sha]:
            if parent in commits:
                children[parent] -= 1
                if not children[parent]:
                    heapq.heappush(ready, (-_moment(commits[parent].get('authored_at')), parent))
    return order


def _in_period(commit, request):
    day = (commit.get('authored_at') or '')[:10]
    return (not request.since or day >= request.since) and (not request.until or day <= request.until)


def select(facts, request):
    """Commits et faits Git vises par la requete ; statut NOT_FOUND ou AMBIGUOUS pour un commit introuvable."""
    commits, attached, parents = _index(facts)
    order = log_order(commits, parents)
    status = SELECTED
    if request.kind == COMMIT:
        chosen = [sha for sha in order if sha.startswith(request.commit)]
        status = SELECTED if len(chosen) == 1 else AMBIGUOUS if chosen else NOT_FOUND
        chosen = chosen if status == SELECTED else []
    elif request.kind in {LATEST, PERIOD}:
        chosen = [sha for sha in order if _in_period(commits[sha], request)]
        chosen = chosen[:request.count] if request.kind == LATEST else chosen
    else:
        chosen = []
    not_interpreted = sorted({fact['subject'] for fact in facts if fact.get('kind') == 'COVERAGE'
                              and fact.get('coverage_type') == 'NOT_INTERPRETED'})
    return {'status': status, 'total_commits': len(commits),
            'commits': [commits[sha] for sha in chosen],
            'facts': [fact for sha in chosen for fact in attached[sha]],
            'not_interpreted': not_interpreted}
