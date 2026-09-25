"""Evaluateur Git (TAXO-EVAL-02, ADR 0007) : l'historique atteignable depuis l'instantane, en faits.

Il observe ; il ne choisit jamais ce qui sera montre. Aucune fenetre de commits n'appartient a son
contrat : il lit tout l'historique atteignable. MAX_COMMITS n'est qu'un budget de lecture ; au-dela,
la suite est declaree NOT_INTERPRETED plutot que tronquee en silence.

Chaque commit donne : le depot HAS_COMMIT le commit (date et message en qualificatifs), le commit
AUTHORED_BY son auteur, CHILD_OF chacun de ses parents et CHANGES chaque fichier touche (compare a son
premier parent). Les fichiers sont des references `file:`, les memes que celles de l'inventaire : c'est
par elles que les faits Git se relient aux faits du code.
"""
from app.evaluations.domain.evaluator import EvaluationOutput
from app.evaluations.domain.status import EvaluationStatus
from app.facts import is_path
from .catalog import CATALOG

MAX_COMMITS = 50000
METHOD = 'git.log'


class GitEvaluator:
    evaluator_id = 'taxo.git'
    producer_version = '0.1.0'
    catalog = CATALOG
    # L'historique decrit l'ascendance de l'instantane, pas son contenu : l'impact d'un commit ne le compare pas.
    describes_content = False

    def __init__(self, max_commits=MAX_COMMITS):
        self.max_commits = max_commits

    def evaluate(self, snapshot):
        repository = f'repository:{snapshot.repository}'
        commits = list(snapshot.history(self.max_commits + 1))
        unread = commits[self.max_commits:]
        facts, invalid = [], []
        for commit in commits[:self.max_commits]:
            facts += self._commit_facts(snapshot, repository, commit, invalid)
        coverage = [self._coverage(repository, 'ANALYSED', repository)]
        warnings = []
        if unread:
            coverage.append(self._coverage(f'commit:{unread[0].sha}', 'NOT_INTERPRETED', repository))
            warnings.append(f'Historique au-delà de {self.max_commits} commits non lu : '
                            f'à partir de commit:{unread[0].sha}')
        for sha, path in invalid:
            coverage.append(self._coverage(f'commit:{sha}', 'NOT_INTERPRETED', repository))
            warnings.append(f'Chemin Git non représentable comme référence : commit:{sha}')
        coverage = list({(item['subject'], item['coverage_type']): item for item in coverage}.values())
        status = EvaluationStatus.PARTIAL if unread or invalid else EvaluationStatus.SUCCESS
        legacy = {'commits_count': min(len(commits), self.max_commits), 'history_complete': not unread}
        return EvaluationOutput(tuple(facts), tuple(coverage), status, tuple(warnings), legacy)

    def _commit_facts(self, snapshot, repository, commit, invalid):
        subject = f'commit:{commit.sha}'
        evidence = {'repository': snapshot.repository, 'commit': snapshot.commit, 'method': METHOD,
                    'object': subject}
        facts = [self._assertion(repository, 'HAS_COMMIT', subject,
                                 {'authored_at': commit.authored_at, 'subject': commit.subject}, evidence)]
        author = (commit.author_email or commit.author_name).strip()
        if author:
            facts.append(self._assertion(subject, 'AUTHORED_BY', f'person:{author}',
                                         {'name': commit.author_name}, evidence))
        for position, parent in enumerate(commit.parents, 1):
            facts.append(self._assertion(subject, 'CHILD_OF', f'commit:{parent}', {'position': position}, evidence))
        for change in commit.changes:
            paths = [change.path] + ([change.old_path] if change.old_path else [])
            if not all(is_path(path) for path in paths):
                invalid.append((commit.sha, change.path))
                continue
            qualifiers = {'change': change.status}
            if change.old_path:
                qualifiers['old_path'] = change.old_path
            facts.append(self._assertion(subject, 'CHANGES', f'file:{change.path}', qualifiers, evidence))
        return facts

    @staticmethod
    def _assertion(subject, relation, object_, qualifiers, evidence):
        return {'contract_version': 1, 'kind': 'ASSERTION', 'status': 'OBSERVED', 'validity': 'VALID',
                'subject': subject, 'relation': relation, 'object': object_, 'qualifiers': qualifiers,
                'evidence': [evidence]}

    @staticmethod
    def _coverage(subject, coverage_type, scope):
        return {'contract_version': 1, 'kind': 'COVERAGE', 'status': 'OBSERVED', 'validity': 'VALID',
                'subject': subject, 'coverage_type': coverage_type, 'scope': {'include': [scope]}}
