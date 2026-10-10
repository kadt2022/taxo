"""Demander a Minia ce que signifie un commit, a partir de ce que Taxo en sait.

Minia ne lit ni le depot ni le code : elle recoit ce que Git sait du commit (auteur, date, message,
fichiers et statuts), les faits changes par le commit (impact de Taxo), leurs preuves et la couverture ; chaque
message passe d'abord par la representation controlee (TAXO-MINIA-SEC-01) : identites pseudonymisees, secrets masques.
Seule exception, a double consentement (TAXO-MINIA-02, ARCHITECTURE § 12.6) : si le reglage MINIA_SOURCE_CONTEXT
vaut `diff` et que la demande l'autorise, le diff du commit est joint, lu par l'historique avec ses refus.
Ce que Git sait est toujours renvoye tel quel, quelle que soit la reponse du modele. Sans fait change et
sans echec d'evaluateur, le modele n'est pas appele : Taxo ne sait rien de plus, et Minia le dit. Aucune
reponse n'est conservee.

Chaque demande se deroule en etapes reelles (TAXO-UX-02) : selection des faits, preparation du contexte,
interpretation. Quand le fournisseur sait diffuser sa reponse, le texte provisoire arrive au fil de l'eau ;
la reponse definitive, citations validees, n'est rendue qu'a la fin.
"""
import inspect
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as StillWaiting

from app.history.domain.errors import NOT_A_GIT_REPOSITORY, HistoryError
from app.minia.application import anchoring
from app.minia.application.protected_model import ProtectedModel
from app.minia.domain import anchors, authorship, briefing, exploration, source_context
from app.minia.domain.confidentiality import Disclosure
from app.minia.domain.cancellation import STOPPED, check
from app.minia.domain.answer import SYSTEM, SYSTEM_SELECTION, SYSTEM_TILE, AnswerStream, parse, with_diff
from app.minia.domain.errors import (CANCELLED, CONFIDENTIALITY_REFUSED, CONTEXT_TOO_LARGE, INVALID_ANSWER,
                                    INVALID_QUESTION, NOT_CONFIGURED, UNKNOWN_PROVIDER, MiniaError)
from app.minia.domain.model import MiniaModel
from app.projection.domain.errors import NO_ANALYSIS, QueryError
from app.projects.application.queries import require_project
from app.projects.domain.project import ProjectError

MAX_QUESTION = 1000
# Garde-fous de l'exploration (ARCHITECTURE § 12.5), fixes par Taxo : une description, au plus 8 operations
# choisies par Minia, puis au plus 10 affirmations verifiees ; l'echange en permet 20.
MAX_CALLS = 8
MAX_CLAIMS = 10
# Budget d'un echange d'exploration : 64 Ko au plus, et jamais plus que la place du modele, moins une marge
# pour la question, la liste des operations et l'enveloppe de chaque tour.
EXCHANGE_BYTES = 64_000
EXCHANGE_MARGIN = 4096
_EXPLORATION_FAILURES = frozenset({INVALID_ANSWER, CONTEXT_TOO_LARGE})
# Chaque reponse de Taxo est bornee a la place qui reste dans la fenetre du modele au tour suivant (moins
# l'enveloppe du tour) ; sous ROOM_TO_CONTINUE octets, Minia doit conclure avec ce qu'elle a.
TURN_MARGIN = 512
ROOM_TO_CONTINUE = 1024
# Pendant qu'un tour attend le modele (un modele local peut mettre plusieurs minutes), un signe de vie part
# regulierement : aucun proxy ne coupe le flux, et seul le delai du fournisseur decide de l'abandon.
HEARTBEAT = 'minia.heartbeat'
HEARTBEAT_SECONDS = 15.0
# Frequence a laquelle l'attente du modele regarde si la demande a ete arretee (TAXO-UX-03).
CANCEL_POLL_SECONDS = 0.25
EXPLORATION, PACKET = 'exploration', 'paquet'
# Reponse donnee par Taxo seul, sans modele (recit TAXO-MINIA-SEC-01, E3) : l'auteur d'un commit, par exemple.
DIRECT = 'taxo'
ANSWERED, NOTHING_KNOWN, NEEDS_SELECTION = 'ANSWERED', 'TAXO_KNOWS_NOTHING', 'NEEDS_SELECTION'
_NOT_REQUESTED = {'status': 'NOT_REQUESTED'}
_DISABLED = {'status': 'DISABLED'}
# En exploration, le diff n'est pas joint d'avance : Minia le demande fichier par fichier (get_diff).
_ON_DEMAND = {'status': 'ON_DEMAND'}
_NOTHING = ("Taxo n'a vu changer aucun fait dans ce commit, parmi ceux que ses évaluateurs savent produire. "
            "Minia ne peut rien affirmer au-delà.")
_SELECT = ("Minia répond sur une sélection de l'historique : précisez un nombre de derniers commits "
           "(« les 3 derniers commits »), un commit ou une période (« depuis 2026-09-01 »).")
# Sans sélection de commits, le repli cherche un élément nommé (récit TAXO-01N / MIP-01 § 5.3).
_NAME_IT = (" Pour une question sur le code, nommez l'élément (`VetController`, `OwnerRepository.findById`) "
            "ou donnez sa référence complète.")
_AMBIGUOUS = 'Plusieurs éléments correspondent à la question ; précisez lequel : {}.'
_UNSEARCHED = ("Taxo n'a pas pu conclure à un seul élément (recherche incomplète ou index des noms absent) : "
               "donnez la référence complète.")
_NOTHING_AROUND = "Taxo ne connaît aucun fait autour de {} dans cette analyse."
_NOT_SERVED = "La Tuile de {} n'a pas pu être servie : {}"
MAX_SHOWN_CANDIDATES = 5
# L'evenement qui clot une demande, avec son resultat.
COMPLETED = 'minia.completed'
_EMPTY = {'SELECTED': "Aucun commit de l'historique analysé ne correspond à cette sélection.",
          'NOT_FOUND': "Aucun commit de l'historique analysé ne commence par cet identifiant.",
          'AMBIGUOUS': 'Plusieurs commits commencent par cet identifiant : donnez-en davantage de caractères.',
          'NO_GIT_FACTS': "La dernière analyse globale ne contient pas de faits Git : relancez-la."}


def _stage(stage, state, label, count=None):
    return 'minia.stage', {'stage': stage, 'state': state, 'label': label, 'count': count}


def _final(events):
    """Resultat d'une demande dont on n'observe pas les etapes : le dernier evenement, `minia.completed`."""
    for event_type, data in events:
        if event_type == COMPLETED:
            return data


def _change(ref, change):
    return {'ref': ref, **{key: change[key] for key in (
        'evaluator_id', 'change', 'kind', 'subject', 'relation', 'before', 'after', 'status',
        'evidence_before', 'evidence_after')}}


def _waiting(call, cancel=None):
    """Rend le resultat de `call()`, en signalant l'attente tous les HEARTBEAT_SECONDS. Une demande arretee
    n'attend plus : l'appel en cours est coupe par le fournisseur, qui s'est inscrit sur le jeton."""
    pool = ThreadPoolExecutor(max_workers=1)
    try:
        future = pool.submit(call)
        waited = since_heartbeat = 0.0
        while True:
            check(cancel)
            try:
                return future.result(timeout=CANCEL_POLL_SECONDS)
            except StillWaiting:
                waited += CANCEL_POLL_SECONDS
                since_heartbeat += CANCEL_POLL_SECONDS
                if since_heartbeat >= HEARTBEAT_SECONDS:
                    since_heartbeat = 0.0
                    yield HEARTBEAT, {'waited_seconds': waited}
    finally:
        # Si le flux est abandonne, le tour en cours s'acheve seul : on ne l'attend pas.
        pool.shutdown(wait=False)


def _accepts(method, name):
    try:
        return name in inspect.signature(method).parameters
    except (TypeError, ValueError):
        return False


def _complete(model, system, user, schema=None, cancel=None):
    """Un tour du modele ; le jeton d'arret lui est confie s'il sait couper son appel."""
    options = {'schema': schema} if schema is not None else {}
    if cancel is not None and _accepts(model.complete, 'cancel'):
        options['cancel'] = cancel
    return model.complete(system, user, **options)


def _reported(events, disclosure):
    """Les etapes d'une demande ; la reponse finale dit ce que Taxo a retenu avant l'envoi au modele, compte,
    jamais montre (recit TAXO-MINIA-SEC-01, E4)."""
    for event_type, data in events:
        if event_type == COMPLETED:
            data = {**data, 'withheld': disclosure.report()}
        yield event_type, data


def _restored(model, answer):
    """La reponse lue d'un paquet, avec les identites d'origine pour l'affichage local."""
    return {**answer, 'answer': model.disclosure.restore(answer['answer']),
            'unknown': model.disclosure.restore(answer['unknown'])}


def _guarded(events, cancel):
    """Les etapes d'une demande, jusqu'a son arret. Ce qui a deja ete fait reste visible (la trajectoire) ;
    apres l'arret, aucune etape ne commence et aucune reponse finale ne part."""
    if cancel is None:
        return events

    def run():
        try:
            for item in events:
                if item[0] == COMPLETED:
                    cancel.check()
                yield item
                cancel.check()
        except Exception as exc:
            # Couper un appel en cours (client ferme) peut lever n'importe ou : apres l'arret, c'est l'arret.
            if cancel.cancelled and getattr(exc, 'code', None) != CANCELLED:
                raise MiniaError(CANCELLED, STOPPED) from exc
            raise
        finally:
            events.close()
    return run()


def _packet(fallback, trajectory):
    """Le mode paquet ; en repli d'une exploration, la raison et le chemin deja parcouru."""
    return {'mode': PACKET, **({'fallback': fallback, 'trajectory': trajectory} if fallback else {})}


def _step(operation, arguments, response):
    """Une etape de la trajectoire, telle que l'humain la voit : l'operation, ses arguments, l'issue, la
    taille du resultat et ce qui n'a pas ete transmis (ARCHITECTURE § 12.5)."""
    entry = {'operation': operation, 'arguments': arguments, 'outcome': response['outcome'],
             'bytes': response['bytes']}
    if response['outcome'] == 'OK':
        entry.update(items=len(response.get('items', [])), not_sent=response.get('not_sent', []))
        if 'verdict' in response:
            entry.update(verdict=response['verdict'], reason=response['reason'])
    else:
        entry['error'] = response['error']
    return entry


def _models(models):
    """Modeles par fournisseur ; un modele seul (ou None) est accepte pour garder l'ancien usage."""
    if models is None:
        return {}
    if isinstance(models, dict):
        return dict(models)
    return {models.provider: models}


def _view(model):
    """Un fournisseur vu du portail : `remote`, ce qu'il recoit quitte la machine ; `data_use`, le service
    peut en outre s'en servir (niveau gratuit)."""
    return {'provider': model.provider, 'model': model.model_name, 'remote': bool(getattr(model, 'remote', False)),
            'data_use': bool(getattr(model, 'data_use', False))}


def _unanchored(resolution):
    """Ce que Taxo dit quand la question ne nomme pas un seul élément : quoi préciser, jamais un choix."""
    if resolution.status == anchors.NONE:
        return _SELECT + _NAME_IT
    if not resolution.candidates:
        return _UNSEARCHED
    shown = ', '.join(resolution.candidates[:MAX_SHOWN_CANDIDATES])
    more = len(resolution.candidates) - MAX_SHOWN_CANDIDATES
    return _AMBIGUOUS.format(shown + (f' et {more} autre(s)' if more > 0 else ''))


class AskMinia:
    """Minia, servie par un ou plusieurs fournisseurs (Ollama, Claude...) : chaque demande peut choisir le sien.

    Quel que soit le fournisseur, le travail est le meme : memes consignes, meme contexte borne, meme
    reponse validee par Taxo. Une reponse n'est jamais un fait.
    """

    def __init__(self, history, models, projects, query=None, source=source_context.OFF, default=None,
                 taxo_query=None, mip=None):
        if source not in source_context.MODES:
            raise ValueError(f'MINIA_SOURCE_CONTEXT invalide : {source} (off ou diff).')
        self.history, self.projects, self.query = history, projects, query
        # Protocole Taxo (ARCHITECTURE § 12) : sans lui, Minia recoit toujours un paquet de contexte.
        self.taxo_query = taxo_query
        # Service MIP (récit TAXO-01N / MIP-01) : la Tuile d'un élément nommé, en repli paquet hors Git.
        self.mip = mip
        self.models, self.source = _models(models), source
        if default is not None and default not in self.models:
            raise ValueError(f'MINIA_PROVIDER : « {default} » n’est pas configuré ({", ".join(self.models) or "aucun"}).')
        self.default = default or next(iter(self.models), None)
        # Demandes en cours, arretables par leur identifiant (TAXO-UX-03) : rien d'autre n'en est garde.
        self._running, self._running_lock = {}, threading.Lock()

    def register(self, cancel):
        """Inscrit une demande en cours ; rend l'identifiant qui permet de l'arreter."""
        request_id = uuid.uuid4().hex
        with self._running_lock:
            self._running[request_id] = cancel
        return request_id

    def release(self, request_id):
        with self._running_lock:
            self._running.pop(request_id, None)

    def stop(self, request_id):
        """Arrete la demande en cours ; False si elle est inconnue ou deja terminee."""
        with self._running_lock:
            cancel = self._running.get(request_id)
        if cancel is None:
            return False
        cancel.cancel()
        return True

    def status(self):
        """Etat de Minia : fournisseur par defaut, fournisseurs disponibles ; `remote` dit si ce qu'elle recoit
        quitte la machine de Taxo."""
        providers = [_view(model) for model in self.models.values()]
        if self.default is None:
            return {'configured': False, 'provider': None, 'model': None, 'source_context': self.source,
                    'remote': False, 'providers': providers}
        return {'configured': True, **_view(self.models[self.default]), 'source_context': self.source,
                'providers': providers}

    def _protected(self, provider, project_id):
        """Le modele de la demande, derriere sa propre protection : tout message y passe avant le fournisseur.
        Les auteurs du projet y sont connus d'avance : une question qui en nomme un ne le transmet pas."""
        model = self._model(provider)
        return ProtectedModel(model, Disclosure(self._authors(project_id)))

    def _authors(self, project_id):
        """Tous les auteurs Git du projet, et pas seulement ceux des derniers commits ; aucun si son historique
        n'est pas lisible (le controle final demeure)."""
        try:
            return tuple(self.history.authors(project_id))
        except ProjectError:
            return ()
        except HistoryError as exc:
            if exc.code == NOT_A_GIT_REPOSITORY:
                return ()  # Sans depot Git, aucun auteur a proteger.
            # Un historique illisible laisserait passer un nom d'auteur que rien n'a appris a masquer.
            raise MiniaError(CONFIDENTIALITY_REFUSED, 'Les auteurs du projet ne sont pas lisibles : Taxo ne peut pas '
                             'garantir leur confidentialité, rien n’est transmis au modèle.') from exc

    def _model(self, provider):
        """Le modele demande, ou celui par defaut ; un fournisseur non configure est refuse."""
        if self.default is None:
            raise MiniaError(NOT_CONFIGURED, 'Minia n’est pas configurée : définir MINIA_OLLAMA_MODEL (et lancer '
                             'Ollama), MINIA_CLAUDE_MODEL (et ANTHROPIC_API_KEY), MINIA_GEMINI_MODEL (et '
                             'GEMINI_API_KEY) ou MINIA_MISTRAL_MODEL (et MISTRAL_API_KEY).')
        name = provider or self.default
        if name not in self.models:
            raise MiniaError(UNKNOWN_PROVIDER, f'Fournisseur de Minia non configuré : {name} '
                             f'(disponibles : {", ".join(self.models)}).')
        return self.models[name]

    @classmethod
    def _exchange_bytes(cls, model):
        """Budget d'un echange d'exploration pour ce modele."""
        capacity = cls._capacity(model, exploration.SYSTEM)
        return EXCHANGE_BYTES if capacity is None else max(min(EXCHANGE_BYTES, capacity - EXCHANGE_MARGIN), 1)

    @staticmethod
    def _capacity(model, system):
        """Place disponible (octets) pour le message, si le fournisseur la connait ; None sinon."""
        capacity = getattr(model, 'capacity', None)
        return None if capacity is None else max(capacity(system), 0)

    @staticmethod
    def _model_view(model, served=None):
        """Fournisseur et modele qui ont repondu ; apres un repli, le modele demande est dit aussi."""
        view = {'configured': True, 'provider': model.provider, 'model': served or model.model_name}
        if served and served != model.model_name:
            view['fallback_from'] = model.model_name
        return view

    @staticmethod
    def _checked(question):
        question = (question or '').strip()
        if not question or len(question) > MAX_QUESTION:
            raise MiniaError(INVALID_QUESTION, f'La question doit compter entre 1 et {MAX_QUESTION} caractères.')
        return question

    def about_commit(self, project_id, sha, question, parent=None, source=False, provider=None):
        return _final(self.about_commit_events(project_id, sha, question, parent, source, provider))

    def about_commit_events(self, project_id, sha, question, parent=None, source=False, provider=None, cancel=None):
        """Valide la demande tout de suite (question, projet, commit, puis fournisseur si un modele sert), puis rend ses etapes.

        `source` : la demande autorise Minia a lire le diff ; il n'est joint que si le reglage le permet.
        `provider` : le fournisseur choisi pour cette demande ; celui par defaut sinon.
        `cancel` : le jeton d'arret de la demande (TAXO-UX-03).
        """
        return _guarded(self._commit_events(project_id, sha, question, parent, source, provider, cancel), cancel)

    def _commit_events(self, project_id, sha, question, parent, source, provider, cancel):
        question = self._checked(question)
        project = require_project(self.projects, project_id)
        commit, base, files = self.history.detail(project_id, sha, parent)
        if authorship.asks_author(question):
            # Taxo repond seul : aucun modele n'est requis, ni meme configure.
            return self._commit_author(question, project, commit, base, files)
        model = self._protected(provider, project_id)
        return _reported(self._commit_route(model, question, project, commit, base, files, source, cancel),
                         model.disclosure)

    def _commit_route(self, model, question, project, commit, base, files, source, cancel):
        project_id = project.id
        if self.taxo_query is not None and getattr(model, 'explores', False):
            try:
                # Le diff n'est lisible dans l'echange que si le reglage et la demande l'autorisent (ARCHITECTURE § 12.6).
                exchange = self.taxo_query.open(project_id, diff_consent=source and self.source == source_context.DIFF,
                                            max_bytes=self._exchange_bytes(model))
            except QueryError as exc:
                if exc.code != NO_ANALYSIS:
                    raise
                # Sans analyse globale, le protocole n'a rien a interroger : le paquet du commit, lui, compare
                # directement les instantanes.
                return self._commit_steps(model, question, project, commit, base, files, source,
                                          fallback=str(exc), trajectory=[], cancel=cancel)
            return self._explore_commit(model, question, project, commit, base, files, source, exchange, cancel)
        return self._commit_steps(model, question, project, commit, base, files, source, cancel=cancel)

    @staticmethod
    def _commit_author(question, project, commit, base, files):
        """L'auteur du commit, dit par Taxo d'apres Git : aucun modele n'est appele, l'identite ne sort pas."""
        yield _stage('facts', 'done', 'Taxo répond d’après Git, sans modèle', 1)
        yield COMPLETED, {'mode': DIRECT, 'status': ANSWERED, 'question': question, 'commit': commit.sha,
                          'parent': base, 'model': {'configured': True, 'provider': None, 'model': None},
                          'source_context': _NOT_REQUESTED, 'project': {'id': project.id, 'name': project.name},
                          'git': briefing.commit_view(commit, base, files), 'files_not_sent': 0,
                          'not_interpreted': [], 'failures': [], 'facts_not_sent': 0, 'rejected_citations': [],
                          'facts': [], 'answer': authorship.commit_answer(commit), 'unknown': ''}

    def _explore_commit(self, model, question, project, commit, base, files, source, exchange, cancel=None):
        """Question sur un commit, en exploration (MINIA-09b) : Taxo commence par ce que Git sait du commit ;
        Minia demande ensuite ses faits changes (`diff_facts`), son diff si l'accord est donne, etc."""
        def packet(reason, trajectory):
            return self._commit_steps(model, question, project, commit, base, files, source,
                                      fallback=reason, trajectory=trajectory, cancel=cancel)

        if commit.parents and base != commit.parents[0]:
            # Le protocole compare un commit a son premier parent : l'autre cote d'une fusion reste au paquet.
            yield from packet('comparaison avec un autre parent que le premier', [])
            return
        allowed = self.source == source_context.DIFF
        sent = _ON_DEMAND if source and allowed else _DISABLED if source else _NOT_REQUESTED
        context = {'commit': f'commit:{commit.sha}', 'parent': f'commit:{base}' if base else None,
                   'diff_readable': exchange.diff_consent}
        result = {'question': question, 'commit': commit.sha, 'parent': base, 'model': self._model_view(model),
                  'source_context': sent, 'project': {'id': project.id, 'name': project.name},
                  'git': briefing.commit_view(commit, base, files), 'files_not_sent': 0, 'not_interpreted': [],
                  'failures': [], 'facts_not_sent': 0, 'rejected_citations': [], 'facts': [], 'answer': '',
                  'unknown': ''}
        yield from self._explore(model, question, exchange, [('get_commit', {'commit': commit.sha})], context,
                                 result, packet, cancel)

    def _diff(self, project, commit, base, budget):
        yield _stage('source', 'running', 'Lecture du diff du commit')
        files, read = self.history.diffs(project.id, commit.sha, base)
        # Le diff peut viser toute la place : le briefing lui retire ensuite ce qu'occupent les faits de Taxo.
        limit = source_context.MAX_DIFF_BYTES if budget is None else min(source_context.MAX_DIFF_BYTES, budget)
        context = source_context.build(files, read, max_bytes=limit)
        yield _stage('source', 'done', 'Lecture du diff du commit', len(context.files))
        return context

    def _commit_steps(self, model, question, project, commit, base, files, source=False, fallback=None,
                      trajectory=None, cancel=None):
        yield _stage('facts', 'running', 'Sélection des faits pertinents')
        _, _, evaluations = self.history.impact(project.id, commit.sha, base)
        diff, sent = None, _NOT_REQUESTED
        with_source = source and self.source == source_context.DIFF
        budget = self._capacity(model, with_diff(SYSTEM) if with_source else SYSTEM)
        if with_source:
            diff = yield from self._diff(project, commit, base, budget)
        elif source:
            sent = _DISABLED
        brief = briefing.build(question, commit, base, evaluations, files, (project.id, project.name), diff, budget)
        if diff is not None:
            sent = diff.summary()
        yield _stage('facts', 'done', 'Sélection des faits pertinents', len(brief.refs))
        yield _stage('context', 'done', 'Préparation du contexte')
        result = {**_packet(fallback, trajectory), 'question': question, 'commit': commit.sha, 'parent': base,
                  'model': self._model_view(model), 'source_context': sent,
                  'project': {'id': project.id, 'name': project.name},
                  'git': briefing.commit_view(commit, base, files), 'files_not_sent': brief.files_truncated,
                  'not_interpreted': list(brief.not_interpreted), 'failures': list(brief.failures),
                  'facts_not_sent': brief.truncated, 'rejected_citations': []}
        if brief.empty:
            yield COMPLETED, {**result, 'status': NOTHING_KNOWN, 'facts': [], 'answer': '', 'unknown': _NOTHING}
            return
        raw, served = yield from self._interpret(model, with_diff(SYSTEM) if brief.diff else SYSTEM, brief,
                                                 len(sent.get('files_sent', ())), cancel)
        answer = _restored(model, parse(raw, brief.refs))
        yield COMPLETED, {**result, 'model': self._model_view(model, served), 'status': ANSWERED, 'answer': answer['answer'], 'unknown': answer['unknown'],
                                  'facts': [_change(ref, brief.refs[ref]) for ref in answer['cited']],
                                  'rejected_citations': answer['rejected']}

    def about_project(self, project_id, question, provider=None):
        return _final(self.about_project_events(project_id, question, provider))

    def about_project_events(self, project_id, question, provider=None, cancel=None):
        """Question sur le projet. Un fournisseur qui sait explorer interroge Taxo operation par operation
        (MINIA-09) ; sinon, ou en repli, la requete selectionne et Minia n'explique que la selection."""
        return _guarded(self._project_events(project_id, question, provider, cancel), cancel)

    def _project_events(self, project_id, question, provider, cancel):
        question = self._checked(question)
        projection = self.query(project_id, question)
        if projection['status'] == 'SELECTED' and authorship.asks_author(question):
            return self._selection_authors(question, projection)
        model = self._protected(provider, project_id)
        return _reported(self._project_route(model, question, projection, cancel), model.disclosure)

    def _project_route(self, model, question, projection, cancel):
        project_id = projection['project']['id']
        if self.taxo_query is not None and getattr(model, 'explores', False):
            exchange = self.taxo_query.open(project_id, max_bytes=self._exchange_bytes(model))

            def packet(reason, trajectory):
                return self._project_steps(model, question, projection, fallback=reason, trajectory=trajectory,
                                           cancel=cancel)
            return self._explore(model, question, exchange, [], None,
                                 self._project_result(model, question, projection), packet, cancel)
        return self._project_steps(model, question, projection, cancel=cancel)

    def _explore(self, model, question, exchange, seeds, context, result, packet, cancel=None):
        """Mode exploration : Taxo ouvre avec `describe` et les operations de depart (`seeds`), Minia demande
        les suivantes, puis Taxo verifie ses affirmations. `packet(raison, trajectoire)` rend le repli."""
        label = 'Minia interroge Taxo'
        yield _stage('exploration', 'running', label, 0)
        capacity = self._capacity(model, exploration.SYSTEM)

        def room(operations, exchanged, calls_left):
            """Octets qu'une reponse de Taxo peut encore occuper sans depasser la fenetre du modele."""
            if capacity is None:
                return None
            text = exploration.message(question, operations, exchanged, calls_left, context)
            return capacity - len(text.encode('utf-8')) - TURN_MARGIN

        def bounded(operation, arguments, space):
            request = {'operation': operation, 'arguments': arguments}
            return request if space is None else {**request, 'max_bytes': max(space, 1)}

        trajectory, exchanged, seen, operations = [], [], set(), []
        for operation, arguments in (('describe', {}), *seeds):
            space = room(operations, exchanged, MAX_CALLS)
            if space is not None:
                # Une operation d'ouverture ne prend que la moitie de la place restante : l'autre moitie reste aux
                # operations que Minia choisira. Pour `describe`, encore la moitie : la liste des operations qu'on
                # en tire, envoyee avec elle, n'est jamais plus grande qu'elle.
                space //= 4 if operation == 'describe' else 2
            check(cancel)
            response = exchange.call(bounded(operation, arguments, space))
            exchanged.append({'operation': operation, 'arguments': arguments, 'response': response})
            trajectory.append(_step(operation, arguments, response))
            yield 'minia.operation', trajectory[-1]
            if response['outcome'] != 'OK':
                # Sans ce point de depart (par exemple un commit absent de la derniere analyse), l'exploration
                # n'a rien sur quoi s'appuyer : Taxo repond en mode paquet.
                yield _stage('exploration', 'done', label, len(trajectory))
                yield from packet(f'{operation} : {response["error"]["message"]}', trajectory)
                return
            if operation == 'describe':
                operations = [item for item in response.get('items', []) if item.get('kind') == 'operation']
        opening = len(trajectory)
        try:
            while True:
                calls_left = MAX_CALLS - (len(trajectory) - opening)
                space = room(operations, exchanged, calls_left)
                if space is not None and space < ROOM_TO_CONTINUE:
                    calls_left = 0  # la fenetre est presque pleine : Minia conclut avec ce qu'elle a
                text = exploration.message(question, operations, exchanged, calls_left, context)
                check(cancel)
                raw = yield from _waiting(
                    lambda: _complete(model, exploration.SYSTEM, text, exploration.STEP_SCHEMA, cancel), cancel)
                # Ce que le modele rend porte des pseudonymes : Taxo travaille sur les valeurs d'origine.
                step = exploration.restored(exploration.parse_step(raw), model.disclosure)
                if isinstance(step, exploration.Answer):
                    break
                if calls_left <= 0 or step.key in seen:
                    raise MiniaError(INVALID_ANSWER, 'Minia ne progressait plus (opération répétée ou limite atteinte).')
                seen.add(step.key)
                check(cancel)
                response = exchange.call(bounded(step.operation, step.arguments, space))
                exchanged.append({'operation': step.operation, 'arguments': step.arguments, 'response': response})
                trajectory.append(_step(step.operation, step.arguments, response))
                yield 'minia.operation', trajectory[-1]
                yield _stage('exploration', 'running', label, len(trajectory))
        except MiniaError as exc:
            if exc.code not in _EXPLORATION_FAILURES:
                raise
            # L'exploration a echoue (format invalide, boucle sans progres, fenetre du modele depassee) : Taxo
            # bascule en mode paquet, qui ajuste son contexte a la place disponible.
            yield _stage('exploration', 'done', label, len(trajectory))
            yield from packet(str(exc), trajectory)
            return
        yield _stage('exploration', 'done', label, len(trajectory))
        statements = yield from self._verified(step.statements, exchange, trajectory, cancel)
        check(cancel)
        yield COMPLETED, {
            **result, 'status': ANSWERED, 'mode': EXPLORATION, 'statements': statements, 'trajectory': trajectory,
            'budget': {'max_bytes': exchange.budget, 'used': exchange.used}}

    @staticmethod
    def _verified(statements, exchange, trajectory, cancel=None):
        """Chaque affirmation de Minia est verifiee par Taxo avant l'affichage ; au-dela de MAX_CLAIMS,
        elle est montree comme non verifiee, jamais comme etablie."""
        claims = sum(1 for item in statements if item['type'] == exploration.CLAIM)
        yield _stage('verification', 'running', 'Taxo vérifie les affirmations de Minia', claims)
        verified, checked = [], 0
        for statement in statements:
            if statement['type'] != exploration.CLAIM:
                verified.append(statement)
                continue
            if checked >= MAX_CLAIMS:
                verified.append({**statement, 'verdict': None, 'error': {
                    'code': 'NOT_VERIFIED', 'message': f'Au-delà de {MAX_CLAIMS} affirmations, Taxo ne vérifie plus.'}})
                continue
            checked += 1
            arguments = {name: value for name, value in statement['claim'].items() if value}
            check(cancel)
            response = exchange.call({'operation': 'verify_claim', 'arguments': arguments})
            trajectory.append(_step('verify_claim', arguments, response))
            yield 'minia.operation', trajectory[-1]
            if response['outcome'] != 'OK':
                verified.append({**statement, 'verdict': None, 'error': response['error']})
                continue
            verified.append({**statement, 'claim': response['claim'], 'verdict': response['verdict'],
                             'reason': response['reason'], 'facts': response['items'],
                             'evidence': response['evidence'], 'not_sent': response['not_sent']})
        yield _stage('verification', 'done', 'Taxo vérifie les affirmations de Minia', claims)
        return verified

    def _project_result(self, model, question, projection):
        return {'question': question, 'model': self._model_view(model), 'project': projection['project'],
                'analysis': projection['analysis'], 'request': projection['request'],
                'selection': projection['status'], 'commits': [], 'total_commits': projection['total_commits'],
                'not_interpreted': [], 'facts_not_sent': 0, 'rejected_citations': [], 'facts': [],
                'answer': '', 'unknown': ''}

    def _project_steps(self, model, question, projection, fallback=None, trajectory=None, cancel=None):
        yield _stage('facts', 'done', 'Sélection des faits pertinents', len(projection['facts']))
        result = {**_packet(fallback, trajectory), 'question': question, 'model': self._model_view(model), 'project': projection['project'],
                  'analysis': projection['analysis'], 'request': projection['request'],
                  'selection': projection['status'], 'commits': projection['commits'],
                  'total_commits': projection['total_commits'], 'not_interpreted': projection['not_interpreted'],
                  'facts_not_sent': 0, 'rejected_citations': [], 'facts': [], 'answer': ''}
        if projection['status'] == 'GLOBAL':
            if self.taxo_query is None or self.mip is None:
                yield COMPLETED, {**result, 'status': NEEDS_SELECTION, 'unknown': _SELECT}
                return
            yield from self._anchored_steps(model, question, projection, result, cancel)
            return
        if not projection['facts']:
            yield COMPLETED, {**result, 'status': NOTHING_KNOWN, 'unknown': _EMPTY[projection['status']]}
            return
        project = projection['project']
        brief = briefing.selection(question, projection, (project['id'], project['name']),
                                   self._capacity(model, SYSTEM_SELECTION))
        yield _stage('context', 'done', 'Préparation du contexte')
        raw, served = yield from self._interpret(model, SYSTEM_SELECTION, brief, cancel=cancel)
        answer = _restored(model, parse(raw, brief.refs))
        yield COMPLETED, {**result, 'model': self._model_view(model, served), 'status': ANSWERED, 'answer': answer['answer'], 'unknown': answer['unknown'],
                                  'facts': [{'ref': ref, **brief.refs[ref]} for ref in answer['cited']],
                                  'facts_not_sent': brief.truncated, 'rejected_citations': answer['rejected']}

    @staticmethod
    def _selection_authors(question, projection):
        """Les auteurs d'une selection de commits, dits par Taxo d'apres ses faits Git, sans modele."""
        text, authored = authorship.selection_answer(projection['facts'])
        yield _stage('facts', 'done', 'Taxo répond d’après Git, sans modèle', len(authored))
        yield COMPLETED, {'mode': DIRECT, 'status': ANSWERED, 'question': question,
                          'model': {'configured': True, 'provider': None, 'model': None},
                          'project': projection['project'], 'analysis': projection['analysis'],
                          'request': projection['request'], 'selection': projection['status'],
                          'commits': projection['commits'], 'total_commits': projection['total_commits'],
                          'not_interpreted': projection['not_interpreted'], 'facts_not_sent': 0,
                          'rejected_citations': [], 'answer': text, 'unknown': '',
                          'facts': [{'ref': f'F{index}', **fact} for index, fact in enumerate(authored, 1)]}

    def locate(self, project_id, question):
        """L'élément que la question nomme, sans modèle (récit TAXO-01N / MIP-01 § 5.1) : son ancre si elle est
        unique, sinon les candidates entre lesquelles choisir ; jamais un choix fait par Taxo."""
        question = self._checked(question)
        exchange = self.taxo_query.open(project_id, max_bytes=EXCHANGE_BYTES)
        resolution = anchoring.drained(anchoring.locate(exchange, question, []))
        return {'question': question, 'analysis': exchange.snapshot['analysis'], 'status': resolution.status,
                'anchor': resolution.anchor, 'candidates': list(resolution.candidates[:MAX_SHOWN_CANDIDATES]),
                'more_candidates': max(len(resolution.candidates) - MAX_SHOWN_CANDIDATES, 0)}

    def _anchored_steps(self, model, question, projection, result, cancel=None):
        """Repli paquet sans sélection de commits : l'ancre explicite de la question, sa Tuile MIP, puis Minia
        n'interprète que cette Tuile. Sans ancre unique, Taxo dit quoi préciser ; le modèle n'est pas appelé."""
        project = projection['project']
        exchange = self.taxo_query.open(project['id'], analysis_id=projection['analysis']['id'],
                                        max_bytes=EXCHANGE_BYTES)
        trajectory = list(result.get('trajectory') or [])
        label = 'Taxo cherche l’élément nommé par la question'
        yield _stage('anchor', 'running', label)
        found = yield from anchoring.anchor(exchange, self.mip, project['id'], question, trajectory,
                                            self._capacity(model, SYSTEM_TILE), cancel)
        resolution = found.resolution
        yield _stage('anchor', 'done', label, len(resolution.candidates))
        result = {**result, 'trajectory': trajectory, 'anchor': {
            'status': resolution.status, 'reference': resolution.anchor,
            'candidates': list(resolution.candidates[:MAX_SHOWN_CANDIDATES])}}
        if resolution.status != anchors.FOUND:
            yield COMPLETED, {**result, 'status': NEEDS_SELECTION, 'unknown': _unanchored(resolution)}
            return
        if found.refused:
            yield COMPLETED, {**result, 'status': NOTHING_KNOWN,
                                      'unknown': _NOT_SERVED.format(resolution.anchor, found.refused)}
            return
        brief = briefing.tile(question, resolution.anchor, found.tiles, (project['id'], project['name']),
                              self._capacity(model, SYSTEM_TILE))
        result = {**result, 'not_interpreted': list(brief.not_interpreted), 'facts_not_sent': brief.truncated}
        if not brief.refs:
            unknown = _NOTHING_AROUND.format(resolution.anchor)
            yield COMPLETED, {**result, 'status': NOTHING_KNOWN, 'unknown': unknown}
            return
        yield _stage('context', 'done', 'Préparation du contexte')
        raw, served = yield from self._interpret(model, SYSTEM_TILE, brief, cancel=cancel)
        answer = _restored(model, parse(raw, brief.refs))
        yield COMPLETED, {**result, 'model': self._model_view(model, served), 'status': ANSWERED,
                                  'answer': answer['answer'], 'unknown': answer['unknown'],
                                  'facts': [{'ref': ref, **brief.refs[ref]} for ref in answer['cited']],
                                  'rejected_citations': answer['rejected']}

    @staticmethod
    def _interpret(model, system, brief, diff_files=0, cancel=None):
        """Texte brut du modele et, si le fournisseur le dit, le modele qui a repondu ; diffuse le texte
        provisoire de la reponse si le fournisseur le permet."""
        label = f'Minia interprète {len(brief.refs)} fait{"s" if len(brief.refs) > 1 else ""} Taxo'
        if diff_files:
            label += f' et le diff de {diff_files} fichier{"s" if diff_files > 1 else ""}'
        yield _stage('interpretation', 'running', label, len(brief.refs))
        stream = getattr(model, 'stream', None)
        served = None
        check(cancel)
        if stream is None:
            raw = yield from _waiting(lambda: _complete(model, system, brief.text, cancel=cancel), cancel)
        else:
            options = {'cancel': cancel} if cancel is not None and _accepts(stream, 'cancel') else {}
            chunks, extractor, pieces = [], AnswerStream(), stream(system, brief.text, **options)
            while True:
                check(cancel)
                try:
                    chunk = next(pieces)
                except StopIteration as end:
                    # Un fournisseur peut rendre, en fin de flux, le modele qui a reellement repondu (repli).
                    served = end.value
                    break
                chunks.append(chunk)
                text = extractor.feed(chunk)
                if text:
                    yield 'minia.delta', {'text': text}
            raw = ''.join(chunks)
        yield _stage('interpretation', 'done', label, len(brief.refs))
        return raw, served
