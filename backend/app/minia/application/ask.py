"""Demander a Minia ce que signifie un commit, a partir de ce que Taxo en sait.

Minia ne lit ni le depot ni le code : elle recoit ce que Git sait du commit (auteur, date, message,
fichiers et statuts), les faits changes par le commit (impact de Taxo), leurs preuves et la couverture.
Ce que Git sait est toujours renvoye tel quel, quelle que soit la reponse du modele. Sans fait change et
sans echec d'evaluateur, le modele n'est pas appele : Taxo ne sait rien de plus, et Minia le dit. Aucune
reponse n'est conservee.
"""
from app.minia.domain import briefing
from app.minia.domain.answer import SYSTEM, SYSTEM_SELECTION, parse
from app.minia.domain.errors import INVALID_QUESTION, NOT_CONFIGURED, MiniaError
from app.minia.domain.model import MiniaModel
from app.projects.application.queries import require_project

MAX_QUESTION = 1000
ANSWERED, NOTHING_KNOWN, NEEDS_SELECTION = 'ANSWERED', 'TAXO_KNOWS_NOTHING', 'NEEDS_SELECTION'
_NOTHING = ("Taxo n'a vu changer aucun fait dans ce commit, parmi ceux que ses évaluateurs savent produire. "
            "Minia ne peut rien affirmer au-delà.")
_SELECT = ("Minia répond sur une sélection de l'historique : précisez un nombre de derniers commits "
           "(« les 3 derniers commits »), un commit ou une période (« depuis 2026-09-01 »).")
_EMPTY = {'SELECTED': "Aucun commit de l'historique analysé ne correspond à cette sélection.",
          'NOT_FOUND': "Aucun commit de l'historique analysé ne commence par cet identifiant.",
          'AMBIGUOUS': 'Plusieurs commits commencent par cet identifiant : donnez-en davantage de caractères.',
          'NO_GIT_FACTS': "La dernière analyse globale ne contient pas de faits Git : relancez-la."}


def _change(ref, change):
    return {'ref': ref, **{key: change[key] for key in (
        'evaluator_id', 'change', 'kind', 'subject', 'relation', 'before', 'after', 'status',
        'evidence_before', 'evidence_after')}}


class AskMinia:
    def __init__(self, history, model: MiniaModel | None, projects, query=None):
        self.history, self.model, self.projects, self.query = history, model, projects, query

    def status(self):
        if self.model is None:
            return {'configured': False, 'provider': None, 'model': None}
        return {'configured': True, 'provider': self.model.provider, 'model': self.model.model_name}

    def _checked(self, question):
        question = (question or '').strip()
        if not question or len(question) > MAX_QUESTION:
            raise MiniaError(INVALID_QUESTION, f'La question doit compter entre 1 et {MAX_QUESTION} caractères.')
        if self.model is None:
            raise MiniaError(NOT_CONFIGURED, 'Minia n’est pas configurée : définir MINIA_OLLAMA_MODEL (et lancer Ollama).')
        return question

    def about_commit(self, project_id, sha, question, parent=None):
        question = self._checked(question)
        project = require_project(self.projects, project_id)
        commit, base, files = self.history.detail(project_id, sha, parent)
        _, _, evaluations = self.history.impact(project_id, sha, base)
        brief = briefing.build(question, commit, base, evaluations, files, (project.id, project.name))
        result = {'question': question, 'commit': commit.sha, 'parent': base, 'model': self.status(),
                  'project': {'id': project.id, 'name': project.name},
                  'git': briefing.commit_view(commit, base, files), 'files_not_sent': brief.files_truncated,
                  'not_interpreted': list(brief.not_interpreted), 'failures': list(brief.failures),
                  'facts_not_sent': brief.truncated, 'rejected_citations': []}
        if brief.empty:
            return {**result, 'status': NOTHING_KNOWN, 'facts': [], 'answer': '', 'unknown': _NOTHING}
        answer = parse(self.model.complete(SYSTEM, brief.text), brief.refs)
        return {**result, 'status': ANSWERED, 'answer': answer['answer'], 'unknown': answer['unknown'],
                'facts': [_change(ref, brief.refs[ref]) for ref in answer['cited']],
                'rejected_citations': answer['rejected']}

    def about_project(self, project_id, question):
        """Question sur l'historique du projet : la requete selectionne, Minia n'explique que la selection."""
        question = self._checked(question)
        projection = self.query(project_id, question)
        result = {'question': question, 'model': self.status(), 'project': projection['project'],
                  'analysis': projection['analysis'], 'request': projection['request'],
                  'selection': projection['status'], 'commits': projection['commits'],
                  'total_commits': projection['total_commits'], 'not_interpreted': projection['not_interpreted'],
                  'facts_not_sent': 0, 'rejected_citations': [], 'facts': [], 'answer': ''}
        if projection['status'] == 'GLOBAL':
            return {**result, 'status': NEEDS_SELECTION, 'unknown': _SELECT}
        if not projection['facts']:
            return {**result, 'status': NOTHING_KNOWN, 'unknown': _EMPTY[projection['status']]}
        project = projection['project']
        brief = briefing.selection(question, projection, (project['id'], project['name']))
        answer = parse(self.model.complete(SYSTEM_SELECTION, brief.text), brief.refs)
        return {**result, 'status': ANSWERED, 'answer': answer['answer'], 'unknown': answer['unknown'],
                'facts': [{'ref': ref, **brief.refs[ref]} for ref in answer['cited']],
                'facts_not_sent': brief.truncated, 'rejected_citations': answer['rejected']}
