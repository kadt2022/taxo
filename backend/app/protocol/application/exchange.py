"""Protocole Taxo, operations v1 (TAXO-QUERY-02, ADR 0009).

Un echange est ouvert sur un projet et sa derniere analyse : l'instantane est fixe a l'ouverture et ne
change plus. Chaque operation est en lecture seule, deterministe, et repond dans l'enveloppe commune.
Les faits recoivent une reference courte (`F1`…), leurs preuves aussi (`E1`…), stables dans l'echange :
seules les references effectivement transmises existent.

Le protocole ne connait ni langage, ni framework, ni projet : il interroge des relations et des
references du contrat (ADR 0002). Ce que sait chaque analyseur vient de son catalogue.
"""
import json
import logging
import re

from app.facts import is_path, is_reference
from app.facts.domain.fact import RELATIONS
from app.history.domain.errors import UNKNOWN_COMMIT, UNKNOWN_PATH, HistoryError
from app.projects.application.queries import require_project
from app.projection.domain.errors import NO_ANALYSIS, QueryError
from app.protocol.domain.envelope import (BUDGET_EXHAUSTED, INTERNAL, INVALID_ARGUMENT, MAX_ERROR_BYTES,
                                          NO_CONSENT, NOT_AVAILABLE, OUT_OF_SCOPE, PROTOCOL, OperationError,
                                          Response, error)
from app.protocol.domain.verdict import Analyzer, contains, judge

logger = logging.getLogger(__name__)

DEFAULT_OPERATION_BYTES = 8_000
MAX_OPERATION_BYTES = 32_000
DEFAULT_EXCHANGE_BYTES = 64_000
MAX_EXCHANGE_BYTES = 200_000
MAX_OPERATIONS = 20
# Chaque operation encore possible garde de quoi repondre par un refus : le budget n'est jamais depasse.
ERROR_RESERVE = MAX_OPERATIONS * MAX_ERROR_BYTES
MIN_EXCHANGE_BYTES = ERROR_RESERVE + 6_000
MAX_ARGUMENT_LENGTH = 1000

NATURES = ('ASSERTION', 'ABSENCE', 'COVERAGE')
V1 = ('describe', 'find_facts', 'get_evidence', 'get_coverage', 'get_commit', 'get_diff', 'verify_claim')
# Operations reservees de l'ADR 0009 que Taxo sait deja servir : `diff_facts` s'appuie sur l'impact d'un
# commit (comparaison des faits des evaluateurs de contenu entre le parent et le commit, TAXO-HIST-01).
ACTIVATED = ('diff_facts',)
OPERATIONS = V1 + ACTIVATED
RESERVED = ('find_endpoint', 'trace_access_control', 'find_callers', 'find_callees', 'find_dependencies',
            'find_configuration', 'get_source')
_ARGUMENTS = {
    'describe': {},
    'find_facts': {'subject': 'reference', 'relation': 'relation', 'object': 'reference ou valeur',
                   'nature': '|'.join(NATURES)},
    'get_evidence': {'fact': 'F…'},
    'get_coverage': {'scope': 'reference (facultatif)'},
    'get_commit': {'commit': 'identifiant, 7 caracteres ou plus'},
    'get_diff': {'commit': 'identifiant, 7 caracteres ou plus', 'path': 'chemin d’un fichier touche'},
    'verify_claim': {'subject': 'reference', 'relation': 'relation', 'object': 'reference ou valeur'},
    'diff_facts': {'commit': 'identifiant, 7 caracteres ou plus'},
}
_LOCATION = ('path', 'line_start', 'line_end', 'symbol', 'method', 'object')
_COMMIT = re.compile(r'[0-9a-f]{7,64}')
# Syntaxe reservee type:cle : une valeur qui la prend est toujours lue comme une reference (ADR 0002).
_REFERENCE_SYNTAX = re.compile(r'[a-z][a-z0-9-]*:')
_HISTORY = 'HAS_COMMIT'
_UNREADABLE = ('NOT_INTERPRETED', 'READ_ERROR')


def _text(arguments, name, required=False):
    value = arguments.get(name)
    if value is None:
        if required:
            raise OperationError(INVALID_ARGUMENT, f'Argument requis : {name}.')
        return None
    if not isinstance(value, str) or not value.strip() or len(value) > MAX_ARGUMENT_LENGTH:
        raise OperationError(INVALID_ARGUMENT, f'Argument invalide : {name}.')
    return value


def _reference(arguments, name, required=False):
    value = _text(arguments, name, required)
    if value is not None and not is_reference(value):
        raise OperationError(INVALID_ARGUMENT, f'{name} doit être une référence du contrat (type:clé).')
    return value


def _relation(arguments, required=False):
    value = _text(arguments, 'relation', required)
    if value is not None and value not in RELATIONS:
        raise OperationError(INVALID_ARGUMENT, f'Relation hors du vocabulaire : {value}.')
    return value


def _no_other(arguments, allowed):
    unknown = sorted(set(arguments) - set(allowed))
    if unknown:
        raise OperationError(INVALID_ARGUMENT, f'Argument inconnu : {", ".join(unknown)}.')


def _claim_object(relation, target):
    """L'objet d'une affirmation doit etre du type que la relation admet (ADR 0002, vocabulaire v1)."""
    _, targets, _ = RELATIONS[relation]
    if bool(targets) != (target is not None):
        raise OperationError(INVALID_ARGUMENT, f'{relation} {"exige" if targets else "n’a pas"} d’objet.')
    if target is None or (relation == 'AUTHORIZED_BY' and not _REFERENCE_SYNTAX.match(target)):
        return
    if not is_reference(target) or target.split(':', 1)[0] not in targets:
        raise OperationError(INVALID_ARGUMENT, f'Objet attendu pour {relation} : {", ".join(sorted(targets))}.')


def _without_evidence(fact):
    return {key: value for key, value in fact.items() if key != 'evidence'}


def _coverage_entry(fact):
    return {'subject': fact['subject'], 'type': fact['coverage_type'], 'scope': fact['scope'],
            'producer': fact.get('produced_by', {}).get('producer_id')}


class References:
    """References courtes d'un echange : un meme fait, une meme reference."""

    def __init__(self):
        self.facts, self.by_key, self.evidence = {}, {}, {}

    @staticmethod
    def _key(fact):
        return json.dumps(fact, sort_keys=True, ensure_ascii=False)

    def fact(self, fact):
        """Reference du fait, et si elle vient d'etre creee."""
        key = self._key(fact)
        if key in self.by_key:
            return self.by_key[key], False
        ref = f'F{len(self.facts) + 1}'
        self.facts[ref], self.by_key[key] = fact, ref
        return ref, True

    def forget(self, ref):
        """Retire la derniere reference creee : son fait n'a pas ete transmis."""
        fact = self.facts.pop(ref)
        del self.by_key[self._key(fact)]

    def proof(self, fact_ref, index):
        key = (fact_ref, index)
        if key not in self.evidence:
            self.evidence[key] = f'E{len(self.evidence) + 1}'
        return self.evidence[key]


class TaxoQuery:
    """Ouvre des echanges du protocole sur les projets analyses."""

    def __init__(self, projects, scans, facts, history, analyzers, source_context):
        # `analyzers` : les evaluateurs enregistres ; seuls leur identifiant et leur catalogue servent.
        self.projects, self.scans, self.facts, self.history = projects, scans, facts, history
        self.catalogs = {item.evaluator_id: frozenset(item.catalog.relations) for item in analyzers}
        self.source_context = source_context

    def open(self, project_id, diff_consent=False, max_bytes=None):
        project = require_project(self.projects, project_id)
        analyses = self.scans.list(project_id)
        if not analyses:
            raise QueryError(NO_ANALYSIS, "Aucune analyse globale pour ce projet : lancez-la d'abord.")
        budget = max(MIN_EXCHANGE_BYTES, min(max_bytes or DEFAULT_EXCHANGE_BYTES, MAX_EXCHANGE_BYTES))
        return Exchange(self, project.id, analyses[0], diff_consent, budget)


class Exchange:
    """Un echange : un projet, une analyse, un budget, des references."""

    def __init__(self, service, project_id, scan, diff_consent, budget):
        self.service, self.project_id, self.scan = service, project_id, scan
        self.diff_allowed = service.source_context == 'diff'
        self.diff_consent = bool(diff_consent) and self.diff_allowed
        self.budget, self.used, self.calls = budget, 0, 0
        self.refs = References()
        evaluations = scan.result.get('evaluations', [])
        reference = next((item['snapshot'] for item in evaluations if item.get('snapshot')), {})
        self.snapshot = {'analysis': scan.id, 'commit': reference.get('commit')}
        self.repository = f'repository:{reference["repository"]}' if reference.get('repository') else None
        self.evaluations = evaluations
        self._coverage = None

    # --- Contexte commun -------------------------------------------------------------------------

    def _query(self, **filters):
        return self.service.facts.query(self.scan.id, **filters)

    def _own(self, *references):
        """Un echange ne franchit jamais la frontiere de son projet : un autre depot est hors perimetre."""
        for value in references:
            if value and value.startswith('repository:') and value != self.repository:
                raise OperationError(OUT_OF_SCOPE, 'Ce dépôt n’est pas celui de cet échange.')

    @property
    def coverage(self):
        if self._coverage is None:
            self._coverage = self._query(kind='COVERAGE')
        return self._coverage

    def analyzers(self):
        found = []
        for item in self.evaluations:
            identifier = item['evaluator_id']
            relations = self.service.catalogs.get(identifier, frozenset(item.get('relations', {})))
            coverage = tuple(fact for fact in self.coverage
                             if fact.get('produced_by', {}).get('producer_id') == identifier)
            found.append(Analyzer(identifier, relations, item.get('status') == 'FAILED', coverage))
        return found

    def _envelope_coverage(self, relation=None, concerned=()):
        """Ou Taxo a cherche : la couverture du depot des analyseurs concernes, et celle des references
        visees. Toujours presente, meme pour un resultat vide."""
        chosen = [item for item in self.analyzers() if relation is None or relation in item.relations]
        entries = [_coverage_entry(fact) for analyzer in chosen for fact in analyzer.coverage
                   if fact['subject'].startswith('repository:') or fact['subject'] in concerned]
        return entries or [{'subject': None, 'type': 'NOT_ANALYSED', 'scope': None, 'producer': None,
                            'relation': relation}]

    def _history_available(self):
        return any(_HISTORY in item.relations and not item.failed for item in self.analyzers())

    def available(self):
        operations = ['describe', 'find_facts', 'get_evidence', 'get_coverage', 'verify_claim']
        if self._history_available():
            operations += ['get_commit', 'diff_facts']
            if self.diff_allowed:
                operations.append('get_diff')
        return [name for name in OPERATIONS if name in operations]

    def _response(self, operation, coverage, max_bytes, **fields):
        response = Response(operation, self.snapshot, coverage, max_bytes, **fields)
        if not response.fits:
            raise OperationError(BUDGET_EXHAUSTED, 'Plus assez de place pour cette réponse et sa couverture.')
        return response

    def _add_fact(self, response, fact, evidence=False):
        """Ajoute un fait (et, sur demande, ses preuves) ; rend False s'il n'a pas tenu."""
        ref, new = self.refs.fact(fact)
        item = {'ref': ref, 'fact': _without_evidence(fact), 'evidence_count': len(fact.get('evidence', []))}
        if not response.add('items', item):
            if new:
                self.refs.forget(ref)
            return False
        if evidence:
            self._add_evidence(response, ref, fact)
        return True

    def _add_evidence(self, response, ref, fact):
        for index, proof in enumerate(fact.get('evidence', [])):
            entry = {'ref': self.refs.proof(ref, index), 'fact': ref, 'location': proof}
            if not response.add('evidence', entry):
                response.skip('evidence', len(fact['evidence']) - index - 1)
                return

    def _add_facts(self, response, facts, evidence=False):
        for index, fact in enumerate(facts):
            if not self._add_fact(response, fact, evidence):
                response.skip('items', len(facts) - index - 1)
                return

    # --- Appel ---------------------------------------------------------------------------------------

    def call(self, request):
        """Rend la reponse d'une operation. Au plus MAX_OPERATIONS appels par echange : au-dela, l'echange
        est clos et l'appel est une erreur de programmation de l'appelant, pas une reponse du protocole."""
        if self.calls >= MAX_OPERATIONS:
            raise RuntimeError(f'Échange clos : au plus {MAX_OPERATIONS} opérations.')
        self.calls += 1
        operation = request.get('operation') if isinstance(request, dict) else None
        # Seul un nom d'operation du protocole est renvoye : jamais une valeur arbitraire de l'appelant.
        operation = operation if operation in OPERATIONS or operation in RESERVED else None
        name = request.get('operation') if isinstance(request, dict) else None
        try:
            if not isinstance(request, dict) or request.get('protocol', PROTOCOL) != PROTOCOL:
                raise OperationError(INVALID_ARGUMENT, f'Protocole attendu : {PROTOCOL}.')
            arguments = request.get('arguments') or {}
            if not isinstance(arguments, dict):
                raise OperationError(INVALID_ARGUMENT, 'Les arguments forment un objet.')
            max_bytes = self._max_bytes(request.get('max_bytes'))
            if operation in RESERVED:
                raise OperationError(NOT_AVAILABLE, f'{operation} attend un analyseur qui le rende possible.')
            if operation is None:
                raise OperationError(INVALID_ARGUMENT, f'Opération inconnue : {str(name)[:100]}.')
            if operation not in self.available():
                if operation == 'get_diff' and self._history_available():
                    raise OperationError(NO_CONSENT, 'La lecture du diff est désactivée pour ce Taxo.')
                raise OperationError(NOT_AVAILABLE, f'{operation} : aucun analyseur ne le nourrit pour ce projet.')
            result = getattr(self, operation)(arguments, max_bytes).close()
        except OperationError as exc:
            result = error(operation, self.snapshot, exc.code, str(exc))
        except HistoryError as exc:
            code = OUT_OF_SCOPE if exc.code in {UNKNOWN_COMMIT, UNKNOWN_PATH} else NOT_AVAILABLE
            result = error(operation, self.snapshot, code, str(exc))
        except Exception:  # une panne de Taxo reste un resultat, jamais une instruction ni un detail interne
            logger.exception('Opération %s en échec', operation)
            result = error(operation, self.snapshot, INTERNAL, 'Taxo n’a pas pu servir cette opération.')
        self.used += result['bytes']
        return result

    def _max_bytes(self, requested):
        if requested is not None and (type(requested) is not int or requested < 1):
            raise OperationError(INVALID_ARGUMENT, 'max_bytes doit être un entier positif.')
        # Ce qui reste, moins la reserve des refus pour les operations suivantes ; toujours >= MAX_ERROR_BYTES.
        remaining = self.budget - self.used - (MAX_OPERATIONS - self.calls) * MAX_ERROR_BYTES
        return min(requested or DEFAULT_OPERATION_BYTES, MAX_OPERATION_BYTES, remaining)

    # --- Operations ----------------------------------------------------------------------------------

    def describe(self, arguments, max_bytes):
        _no_other(arguments, ())
        response = self._response('describe', self._envelope_coverage(), max_bytes,
                                  consent={'diff': self.diff_consent})
        for name in self.available():
            response.add('items', {'kind': 'operation', 'operation': name, 'arguments': _ARGUMENTS[name]})
        for analyzer, evaluation in zip(self.analyzers(), self.evaluations):
            response.add('items', {'kind': 'analyzer', 'analyzer': analyzer.analyzer_id,
                                   'status': evaluation.get('status'), 'relations': sorted(analyzer.relations)})
        present = {}
        for evaluation in self.evaluations:
            for relation, count in evaluation.get('relations', {}).items():
                present[relation] = present.get(relation, 0) + count
        for relation in sorted(present):
            sources, targets, _ = RELATIONS.get(relation, (set(), set(), set()))
            response.add('items', {'kind': 'relation', 'relation': relation, 'count': present[relation],
                                   'subject_types': sorted(sources), 'object_types': sorted(targets)})
        return response

    def find_facts(self, arguments, max_bytes):
        _no_other(arguments, ('subject', 'relation', 'object', 'nature'))
        subject, relation = _reference(arguments, 'subject'), _relation(arguments)
        target, nature = _text(arguments, 'object'), _text(arguments, 'nature')
        if nature is not None and nature not in NATURES:
            raise OperationError(INVALID_ARGUMENT, f'nature : {", ".join(NATURES)}.')
        if not any((subject, relation, target, nature)):
            raise OperationError(INVALID_ARGUMENT, 'Au moins un de subject, relation, object ou nature.')
        self._own(subject, target)
        facts = self._query(subject=subject, relation=relation, object=target, kind=nature)
        coverage = self._envelope_coverage(relation, {subject, target} - {None})
        response = self._response('find_facts', coverage, max_bytes, count=len(facts))
        self._add_facts(response, facts)
        return response

    def get_evidence(self, arguments, max_bytes):
        _no_other(arguments, ('fact',))
        ref = _text(arguments, 'fact', required=True)
        if ref not in self.refs.facts:
            raise OperationError(INVALID_ARGUMENT, f'{ref} n’a pas été transmis dans cet échange.')
        fact = self.refs.facts[ref]
        producer = fact.get('produced_by', {}).get('producer_id')
        coverage = [entry for entry in self._envelope_coverage(fact.get('relation'), {fact.get('subject')})
                    if entry['producer'] in (producer, None)]
        response = self._response('get_evidence', coverage, max_bytes, fact=ref)
        self._add_evidence(response, ref, fact)
        return response

    def get_coverage(self, arguments, max_bytes):
        _no_other(arguments, ('scope',))
        scope = _reference(arguments, 'scope')
        self._own(scope)
        facts = [fact for fact in self.coverage if scope is None or contains(scope, fact['subject'])]
        # Ce qui n'a pas ete lu passe avant ce qui l'a ete : c'est la limite de ce que Taxo sait.
        facts.sort(key=lambda fact: fact['coverage_type'] not in _UNREADABLE)
        response = self._response('get_coverage', self._envelope_coverage(), max_bytes, count=len(facts))
        self._add_facts(response, facts)
        return response

    def _commit(self, arguments):
        value = _text(arguments, 'commit', required=True).lower()
        if not _COMMIT.fullmatch(value):
            raise OperationError(INVALID_ARGUMENT, 'commit : identifiant hexadécimal de 7 caractères ou plus.')
        if len(value) in (40, 64):
            found = self._query(relation=_HISTORY, object=f'commit:{value}')
        else:
            found = [fact for fact in self._query(relation=_HISTORY) if fact['object'].startswith(f'commit:{value}')]
        shas = sorted({fact['object'] for fact in found})
        if not shas:
            raise OperationError(OUT_OF_SCOPE, 'Ce commit n’appartient pas à l’historique de cette analyse.')
        if len(shas) > 1:
            raise OperationError(INVALID_ARGUMENT, 'Identifiant ambigu : donner plus de caractères.')
        return shas[0], found[0]

    def get_commit(self, arguments, max_bytes):
        _no_other(arguments, ('commit',))
        reference, head = self._commit(arguments)
        facts = [head, *self._query(subject=reference)]
        response = self._response('get_commit', self._envelope_coverage(_HISTORY), max_bytes,
                                  commit=reference, count=len(facts))
        self._add_facts(response, facts)
        return response

    def get_diff(self, arguments, max_bytes):
        _no_other(arguments, ('commit', 'path'))
        if not self.diff_consent:
            raise OperationError(NO_CONSENT, 'La lecture du diff n’a pas été autorisée pour cet échange.')
        reference, _ = self._commit(arguments)
        path = _text(arguments, 'path', required=True)
        if not is_path(path):
            raise OperationError(INVALID_ARGUMENT, 'path : chemin relatif du dépôt, séparateurs /.')
        if not self._query(subject=reference, relation='CHANGES', object=f'file:{path}'):
            raise OperationError(OUT_OF_SCOPE, 'Ce fichier n’est pas touché par ce commit.')
        diff = self.service.history.diff(self.project_id, reference.split(':', 1)[1], path)
        fields = {'commit': reference, 'path': path, 'status': diff['status']}
        if diff['old_path']:
            fields['old_path'] = diff['old_path']
        response = self._response('get_diff', self._envelope_coverage(_HISTORY), max_bytes, **fields)
        if not diff['displayable']:
            response.not_sent({'what': 'diff', 'reason': diff['reason']})
            return response
        for index, hunk in enumerate(diff['hunks']):
            if not response.add('items', _hunk(hunk)):
                response.skip('items', len(diff['hunks']) - index - 1)
                break
        return response

    def diff_facts(self, arguments, max_bytes):
        """Les faits que le commit introduit, modifie ou retire, selon les evaluateurs de contenu compares
        entre son premier parent et lui. Ce sont des changements, pas des faits de l'analyse : ils n'ont pas
        de reference `F…`, et leurs preuves sont des localisations."""
        _no_other(arguments, ('commit',))
        reference, _ = self._commit(arguments)
        _, base, evaluations = self.service.history.impact(self.project_id, reference.split(':', 1)[1])
        coverage = [{'subject': self.repository, 'type': 'ANALYSED' if item['comparable'] else 'NOT_INTERPRETED',
                     'scope': None, 'producer': item['evaluator_id'],
                     'not_interpreted': item['not_interpreted_after']} for item in evaluations]
        changes = [_change(change, item['evaluator_id']) for item in evaluations for change in item['changes']]
        response = self._response('diff_facts', coverage or self._envelope_coverage(), max_bytes,
                                  commit=reference, parent=f'commit:{base}' if base else None, count=len(changes))
        for index, change in enumerate(changes):
            if not response.add('items', change):
                response.skip('items', len(changes) - index - 1)
                break
        return response

    def verify_claim(self, arguments, max_bytes):
        _no_other(arguments, ('subject', 'relation', 'object'))
        subject = _reference(arguments, 'subject', required=True)
        relation = _relation(arguments, required=True)
        target = _text(arguments, 'object')
        sources, _, _ = RELATIONS[relation]
        if subject.split(':', 1)[0] not in sources:
            raise OperationError(INVALID_ARGUMENT, f'{relation} ne s’applique pas à ce type de sujet.')
        _claim_object(relation, target)
        self._own(subject, target)
        claim = {'subject': subject, 'relation': relation}
        if target is not None:
            claim['object'] = target
        established = [fact for fact in self._query(subject=subject, relation=relation, kind='ASSERTION')
                       if fact.get('validity', 'VALID') == 'VALID']
        verdict = judge(claim, established, self.analyzers())
        response = self._response('verify_claim', self._envelope_coverage(relation, {subject, target} - {None}),
                                  max_bytes, claim=claim, verdict=verdict.verdict, reason=verdict.reason)
        self._add_facts(response, list(verdict.facts), evidence=True)
        return response


def _change(change, producer):
    """Un changement de fait, compact : ce qui change, avant, apres, et ou sont les preuves."""
    located = [{key: proof[key] for key in _LOCATION if key in proof}
               for proof in change['evidence_before'] + change['evidence_after']]
    return {'kind': 'change', 'change': change['change'], 'nature': change['kind'], 'subject': change['subject'],
            'relation': change['relation'], 'before': change['before'], 'after': change['after'],
            'status': change['status'], 'producer': producer, 'evidence': located}


def _side(rows, side):
    return '\n'.join(row[side]['text'] for row in rows if row[side] is not None)


def _hunk(hunk):
    return {'before_start': hunk['before_start'], 'after_start': hunk['after_start'],
            'before': _side(hunk['rows'], 'before'), 'after': _side(hunk['rows'], 'after')}
