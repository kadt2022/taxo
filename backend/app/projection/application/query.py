"""Interroger ce que Taxo sait d'un projet (TAXO-QUERY-01).

Les evaluateurs observent pendant l'analyse globale ; Taxo conserve leurs faits ; la requete selectionne
ensuite parmi eux, sans relire le depot. Une requete globale rend l'analyse globale, jamais une liste de
commits.
"""
from app.projects.application.queries import require_project
from app.projection.domain.errors import NO_ANALYSIS, QueryError
from app.projection.domain.projection import select
from app.projection.domain.request import GLOBAL, parse

GIT_EVALUATOR = 'taxo.git'
NO_GIT_FACTS = 'NO_GIT_FACTS'


class ProjectQuery:
    def __init__(self, projects, scans, facts):
        self.projects, self.scans, self.facts = projects, scans, facts

    def __call__(self, project_id, text):
        request = parse(text)
        project = require_project(self.projects, project_id)
        analyses = self.scans.list(project_id)
        if not analyses:
            raise QueryError(NO_ANALYSIS, "Aucune analyse globale pour ce projet : lancez-la d'abord.")
        scan = analyses[0]
        evaluations = scan.result.get('evaluations', [])
        result = {'project': {'id': project.id, 'name': project.name},
                  'analysis': {'id': scan.id, 'created_at': scan.created_at}, 'request': request.as_dict()}
        if request.kind == GLOBAL:
            return {**result, 'status': GLOBAL, 'evaluations': evaluations, 'total_commits': None,
                    'commits': [], 'facts': [], 'not_interpreted': []}
        git = next((item for item in evaluations if item.get('evaluator_id') == GIT_EVALUATOR), None)
        if git is None or git.get('status') == 'FAILED':
            return {**result, 'status': NO_GIT_FACTS, 'evaluations': evaluations, 'total_commits': None,
                    'commits': [], 'facts': [], 'not_interpreted': []}
        projection = select(self.facts.query(scan.id, evaluator_id=GIT_EVALUATOR), request)
        return {**result, 'evaluations': [git], **projection}
