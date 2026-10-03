"""L'impact d'un commit depuis la memoire (TAXO-01F, tranche E) : sans instantane ouvert ni evaluateur execute.

Si le commit et son parent ont chacun une analyse enregistree, leurs faits persistes sont compares, evaluateur
de contenu par evaluateur, avec les regles de comparabilite de la comparaison (echec, catalogue, contrat inconnu,
rien a lire). Le resultat garde la forme historique de l'impact : un fait dont seule la preuve se deplace reste
inchange, comme quand le depot est relu.

Choix automatique, deterministe : pour chaque commit, la plus recente analyse complete du projet en mode
`COMMIT` de ce commit exact ; la plus recente selon sa date d'enregistrement, puis son identifiant. Il manque
l'une des deux : le depot est relu, et la reponse le dit. Une paire demandee explicitement n'est jamais
remplacee par une relecture : incompatible, elle est refusee.
"""
from app.comparison.application.analyses import snapshot
from app.facts import fact_identity
from app.history.domain.errors import INCOMPATIBLE_ANALYSES, UNKNOWN_ANALYSIS, HistoryError
from app.history.domain.impact import compare
from app.snapshots.domain.mode import COMMIT

MEMORY, REREAD = 'MEMORY', 'REREAD'
ANALYSIS, READING = 'ANALYSIS', 'REREAD'


def _commit_of(scan):
    recorded = snapshot(scan) or {}
    return recorded.get('commit') if recorded.get('mode') == COMMIT else None


def recorded(scan):
    """Une analyse persistee, nommee pour que la reponse dise exactement ce qui a servi."""
    return {'kind': ANALYSIS, 'id': scan.id, 'commit': _commit_of(scan), 'created_at': scan.created_at}


def reread(commit):
    """Une lecture temporaire du depot a ce commit : aucune analyse n'est enregistree."""
    return {'kind': READING, 'id': None, 'commit': commit, 'created_at': None}


class RecordedImpact:
    def __init__(self, scans, comparison):
        self.scans, self.comparison = scans, comparison

    def pair(self, project_id, sha, base, before=None, after=None):
        """Les analyses (parent, commit) a comparer ; None s'il faut relire le depot."""
        if before is not None or after is not None:
            return self._explicit(project_id, sha, base, before, after)
        if base is None:
            return None
        found = self._latest(project_id, {base, sha})
        if base not in found or sha not in found:
            return None
        return found[base], found[sha]

    def _latest(self, project_id, commits):
        found = {}
        for scan in self.scans.list(project_id):
            commit = _commit_of(scan)
            if commit in commits and (commit not in found or _newer(scan, found[commit])):
                found[commit] = scan
        return found

    def _explicit(self, project_id, sha, base, before, after):
        if before is None or after is None:
            raise HistoryError(INCOMPATIBLE_ANALYSES, 'Nommer les deux analyses : celle du parent et celle du commit.')
        pair = []
        for analysis, expected, side in ((before, base, 'du parent'), (after, sha, 'du commit')):
            scan = self.scans.get(project_id, analysis)
            if scan is None:
                raise HistoryError(UNKNOWN_ANALYSIS, f'Analyse {analysis} introuvable pour ce projet, ou interrompue.')
            if expected is None or _commit_of(scan) != expected:
                raise HistoryError(INCOMPATIBLE_ANALYSES,
                                   f"L'analyse {analysis} n'est pas une analyse en mode COMMIT {side} "
                                   f'({expected or "aucun parent"}).')
            pair.append(scan)
        return tuple(pair)

    def evaluations(self, before, after, evaluators):
        """Chaque evaluateur de contenu, dans la forme historique de l'impact."""
        identifiers = [evaluator.evaluator_id for evaluator in evaluators]
        found = self.comparison.facts_changed(before, after, identifiers)
        statuses = [_summaries(scan) for scan in (before, after)]
        return [_evaluation(identifier, found[identifier], *statuses) for identifier in identifiers]


def _newer(scan, other):
    return (scan.created_at, scan.id) > (other.created_at, other.id)


def _summaries(scan):
    return {item.get('evaluator_id'): item for item in scan.result.get('evaluations', [])}


def _evaluation(identifier, found, before, after):
    left, right = before.get(identifier, {}), after.get(identifier, {})
    result = {'evaluator_id': identifier, 'producer_version': right.get('producer_version'),
              'status_before': left.get('status'), 'status_after': right.get('status'),
              'comparable': found['reason'] is None, 'reason': found['reason'],
              'not_interpreted_before': found['unread']['before'], 'not_interpreted_after': found['unread']['after']}
    if found['reason'] is not None:
        warnings = [warning for side in (left, right) if side.get('status') == 'FAILED'
                    for warning in side.get('warnings', [])]
        return result | {'failures': [found['message'], *warnings], 'changes': [], 'unchanged_count': 0}
    changes, _ = compare(found['before'], found['after'], fact_identity)
    return result | {'failures': [], 'changes': changes, 'unchanged_count': found['unchanged']}
