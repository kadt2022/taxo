"""Demander a Minia ce que signifie un commit, a partir de ce que Taxo en sait.

Minia ne lit ni le depot ni le code : elle recoit ce que Git sait du commit (auteur, date, message,
fichiers et statuts), les faits changes par le commit (impact de Taxo), leurs preuves et la couverture.
Seule exception, a double consentement (TAXO-MINIA-02, ADR 0008) : si le reglage MINIA_SOURCE_CONTEXT
vaut `diff` et que la demande l'autorise, le diff du commit est joint, lu par l'historique avec ses refus.
Ce que Git sait est toujours renvoye tel quel, quelle que soit la reponse du modele. Sans fait change et
sans echec d'evaluateur, le modele n'est pas appele : Taxo ne sait rien de plus, et Minia le dit. Aucune
reponse n'est conservee.

Chaque demande se deroule en etapes reelles (TAXO-UX-02) : selection des faits, preparation du contexte,
interpretation. Quand le fournisseur sait diffuser sa reponse, le texte provisoire arrive au fil de l'eau ;
la reponse definitive, citations validees, n'est rendue qu'a la fin.
"""
from app.minia.domain import briefing, source_context
from app.minia.domain.answer import SYSTEM, SYSTEM_SELECTION, AnswerStream, parse, with_diff
from app.minia.domain.errors import INVALID_QUESTION, NOT_CONFIGURED, MiniaError
from app.minia.domain.model import MiniaModel
from app.projects.application.queries import require_project

MAX_QUESTION = 1000
ANSWERED, NOTHING_KNOWN, NEEDS_SELECTION = 'ANSWERED', 'TAXO_KNOWS_NOTHING', 'NEEDS_SELECTION'
_NOT_REQUESTED = {'status': 'NOT_REQUESTED'}
_DISABLED = {'status': 'DISABLED'}
_NOTHING = ("Taxo n'a vu changer aucun fait dans ce commit, parmi ceux que ses évaluateurs savent produire. "
            "Minia ne peut rien affirmer au-delà.")
_SELECT = ("Minia répond sur une sélection de l'historique : précisez un nombre de derniers commits "
           "(« les 3 derniers commits »), un commit ou une période (« depuis 2026-09-01 »).")
_EMPTY = {'SELECTED': "Aucun commit de l'historique analysé ne correspond à cette sélection.",
          'NOT_FOUND': "Aucun commit de l'historique analysé ne commence par cet identifiant.",
          'AMBIGUOUS': 'Plusieurs commits commencent par cet identifiant : donnez-en davantage de caractères.',
          'NO_GIT_FACTS': "La dernière analyse globale ne contient pas de faits Git : relancez-la."}


def _stage(stage, state, label, count=None):
    return 'minia.stage', {'stage': stage, 'state': state, 'label': label, 'count': count}


def _final(events):
    """Resultat d'une demande dont on n'observe pas les etapes : le dernier evenement, `minia.completed`."""
    for event_type, data in events:
        if event_type == 'minia.completed':
            return data


def _change(ref, change):
    return {'ref': ref, **{key: change[key] for key in (
        'evaluator_id', 'change', 'kind', 'subject', 'relation', 'before', 'after', 'status',
        'evidence_before', 'evidence_after')}}


class AskMinia:
    def __init__(self, history, model: MiniaModel | None, projects, query=None, source=source_context.OFF):
        if source not in source_context.MODES:
            raise ValueError(f'MINIA_SOURCE_CONTEXT invalide : {source} (off ou diff).')
        self.history, self.model, self.projects, self.query = history, model, projects, query
        self.source = source

    def status(self):
        """Etat de Minia ; `remote` dit si ce qu'elle recoit quitte la machine de Taxo."""
        if self.model is None:
            return {'configured': False, 'provider': None, 'model': None, 'source_context': self.source,
                    'remote': False}
        return {'configured': True, 'provider': self.model.provider, 'model': self.model.model_name,
                'source_context': self.source, 'remote': bool(getattr(self.model, 'remote', False))}

    def _capacity(self, system):
        """Place disponible (octets) pour le message, si le fournisseur la connait ; None sinon."""
        capacity = getattr(self.model, 'capacity', None)
        return None if capacity is None else max(capacity(system), 0)

    def _model_view(self):
        return {key: value for key, value in self.status().items() if key in ('configured', 'provider', 'model')}

    def _checked(self, question):
        question = (question or '').strip()
        if not question or len(question) > MAX_QUESTION:
            raise MiniaError(INVALID_QUESTION, f'La question doit compter entre 1 et {MAX_QUESTION} caractères.')
        if self.model is None:
            raise MiniaError(NOT_CONFIGURED, 'Minia n’est pas configurée : définir MINIA_OLLAMA_MODEL (et lancer Ollama).')
        return question

    def about_commit(self, project_id, sha, question, parent=None, source=False):
        return _final(self.about_commit_events(project_id, sha, question, parent, source))

    def about_commit_events(self, project_id, sha, question, parent=None, source=False):
        """Valide la demande tout de suite (question, projet, commit), puis rend ses etapes a observer.

        `source` : la demande autorise Minia a lire le diff ; il n'est joint que si le reglage le permet.
        """
        question = self._checked(question)
        project = require_project(self.projects, project_id)
        commit, base, files = self.history.detail(project_id, sha, parent)
        return self._commit_steps(question, project, commit, base, files, source)

    def _diff(self, project, commit, base, budget):
        yield _stage('source', 'running', 'Lecture du diff du commit')
        files, read = self.history.diffs(project.id, commit.sha, base)
        # Le diff peut viser toute la place : le briefing lui retire ensuite ce qu'occupent les faits de Taxo.
        limit = source_context.MAX_DIFF_BYTES if budget is None else min(source_context.MAX_DIFF_BYTES, budget)
        context = source_context.build(files, read, max_bytes=limit)
        yield _stage('source', 'done', 'Lecture du diff du commit', len(context.files))
        return context

    def _commit_steps(self, question, project, commit, base, files, source=False):
        yield _stage('facts', 'running', 'Sélection des faits pertinents')
        _, _, evaluations = self.history.impact(project.id, commit.sha, base)
        diff, sent = None, _NOT_REQUESTED
        with_source = source and self.source == source_context.DIFF
        budget = self._capacity(with_diff(SYSTEM) if with_source else SYSTEM)
        if with_source:
            diff = yield from self._diff(project, commit, base, budget)
        elif source:
            sent = _DISABLED
        brief = briefing.build(question, commit, base, evaluations, files, (project.id, project.name), diff, budget)
        if diff is not None:
            sent = diff.summary()
        yield _stage('facts', 'done', 'Sélection des faits pertinents', len(brief.refs))
        yield _stage('context', 'done', 'Préparation du contexte')
        result = {'question': question, 'commit': commit.sha, 'parent': base, 'model': self._model_view(),
                  'source_context': sent,
                  'project': {'id': project.id, 'name': project.name},
                  'git': briefing.commit_view(commit, base, files), 'files_not_sent': brief.files_truncated,
                  'not_interpreted': list(brief.not_interpreted), 'failures': list(brief.failures),
                  'facts_not_sent': brief.truncated, 'rejected_citations': []}
        if brief.empty:
            yield 'minia.completed', {**result, 'status': NOTHING_KNOWN, 'facts': [], 'answer': '', 'unknown': _NOTHING}
            return
        raw = yield from self._interpret(with_diff(SYSTEM) if brief.diff else SYSTEM, brief, len(sent.get('files_sent', ())))
        answer = parse(raw, brief.refs)
        yield 'minia.completed', {**result, 'status': ANSWERED, 'answer': answer['answer'], 'unknown': answer['unknown'],
                                  'facts': [_change(ref, brief.refs[ref]) for ref in answer['cited']],
                                  'rejected_citations': answer['rejected']}

    def about_project(self, project_id, question):
        return _final(self.about_project_events(project_id, question))

    def about_project_events(self, project_id, question):
        """Question sur l'historique du projet : la requete selectionne, Minia n'explique que la selection."""
        question = self._checked(question)
        projection = self.query(project_id, question)
        return self._project_steps(question, projection)

    def _project_steps(self, question, projection):
        yield _stage('facts', 'done', 'Sélection des faits pertinents', len(projection['facts']))
        result = {'question': question, 'model': self._model_view(), 'project': projection['project'],
                  'analysis': projection['analysis'], 'request': projection['request'],
                  'selection': projection['status'], 'commits': projection['commits'],
                  'total_commits': projection['total_commits'], 'not_interpreted': projection['not_interpreted'],
                  'facts_not_sent': 0, 'rejected_citations': [], 'facts': [], 'answer': ''}
        if projection['status'] == 'GLOBAL':
            yield 'minia.completed', {**result, 'status': NEEDS_SELECTION, 'unknown': _SELECT}
            return
        if not projection['facts']:
            yield 'minia.completed', {**result, 'status': NOTHING_KNOWN, 'unknown': _EMPTY[projection['status']]}
            return
        project = projection['project']
        brief = briefing.selection(question, projection, (project['id'], project['name']),
                                   self._capacity(SYSTEM_SELECTION))
        yield _stage('context', 'done', 'Préparation du contexte')
        raw = yield from self._interpret(SYSTEM_SELECTION, brief)
        answer = parse(raw, brief.refs)
        yield 'minia.completed', {**result, 'status': ANSWERED, 'answer': answer['answer'], 'unknown': answer['unknown'],
                                  'facts': [{'ref': ref, **brief.refs[ref]} for ref in answer['cited']],
                                  'facts_not_sent': brief.truncated, 'rejected_citations': answer['rejected']}

    def _interpret(self, system, brief, diff_files=0):
        """Texte brut du modele ; diffuse le texte provisoire de la reponse si le fournisseur le permet."""
        label = f'Minia interprète {len(brief.refs)} fait{"s" if len(brief.refs) > 1 else ""} Taxo'
        if diff_files:
            label += f' et le diff de {diff_files} fichier{"s" if diff_files > 1 else ""}'
        yield _stage('interpretation', 'running', label, len(brief.refs))
        stream = getattr(self.model, 'stream', None)
        if stream is None:
            raw = self.model.complete(system, brief.text)
        else:
            chunks, extractor = [], AnswerStream()
            for chunk in stream(system, brief.text):
                chunks.append(chunk)
                text = extractor.feed(chunk)
                if text:
                    yield 'minia.delta', {'text': text}
            raw = ''.join(chunks)
        yield _stage('interpretation', 'done', label, len(brief.refs))
        return raw
