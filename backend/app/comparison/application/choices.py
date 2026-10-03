"""Choisir les deux analyses a comparer (TAXO-01F, tranche C) : un cas d'usage a part de la comparaison.

Chaque analyse complete du projet est decrite assez pour etre reconnue : son instantane, son commit tel que ses
propres faits Git le disent, ce qu'elle a enregistre et ses evaluateurs en echec. Le depot n'est jamais relu.
"""
from app.comparison.application.analyses import described, snapshot
from app.projects.application.queries import require_project


class AnalysisChoices:
    def __init__(self, projects, scans, store):
        self.projects, self.scans, self.store = projects, scans, store

    def __call__(self, project_id):
        """The complete analyses of the project, newest first, each described enough to be recognised.

        The commit is described from the analysis's own Git facts, never by reading the repository again.
        """
        require_project(self.projects, project_id)
        return [self._choice(scan) for scan in self.scans.list(project_id)]

    def _choice(self, scan):
        sha = (snapshot(scan) or {}).get('commit')
        evaluations = scan.result.get('evaluations', [])
        return {**described(scan), 'commit': self.store.commit(scan.id, sha) if sha else None,
                'fact_count': sum(item.get('fact_count') or 0 for item in evaluations),
                'failed': sorted(item.get('evaluator_id') for item in evaluations if item.get('status') == 'FAILED')}
