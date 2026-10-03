"""First explicit tile: bounded, indexed one-hop selection over persisted facts.

No parser, repository reader, model or implicit reverse relation. Coverage summaries are
labelled as analysis-wide: they cannot establish the absence of a runtime relationship.
"""
import base64
import hashlib
import json

from app.facts import is_reference
from app.evaluations.domain.capability import Reads, languages_complete
from app.protocol.domain.verdict import Analyzer, not_analysed, unknown_languages
from app.facts.domain.fact import RELATIONS
from app.protocol.domain.envelope import (BUDGET_EXHAUSTED, INVALID_ARGUMENT,
                                          OperationError, Response, size)

VERSION = 'neighborhood/1'
_FIELDS = {'analysis', 'root', 'follow', 'direction', 'depth', 'priority', 'max_nodes', 'max_edges',
           'max_work', 'continuation'}

_TYPE = 'coverage_type'


def _invalid(message):
    raise OperationError(INVALID_ARGUMENT, message)


def _integer(arguments, name, default, maximum):
    value = arguments.get(name, default)
    if type(value) is not int or not 1 <= value <= maximum:
        _invalid(f'{name} doit être un entier entre 1 et {maximum}.')
    return value


def _relations(value):
    if (not isinstance(value, list) or not 1 <= len(value) <= 16
            or any(not isinstance(item, str) or item not in RELATIONS for item in value)
            or len(set(value)) != len(value)):
        _invalid('follow : 1 à 16 relations distinctes du vocabulaire.')
    return value


def _cursor(binding, position, after):
    raw = json.dumps([binding, position, after], separators=(',', ':')).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip('=')


def _resume(token, binding, count):
    if token is None:
        return 0, ''
    if not isinstance(token, str) or len(token) > 16000:
        _invalid('Reprise invalide.')
    try:
        values = json.loads(base64.b64decode(token + '=' * (-len(token) % 4), altchars=b'-_', validate=True))
        valid = (isinstance(values, list) and len(values) == 3 and values[0] == binding
                 and type(values[1]) is int and 0 <= values[1] < count
                 and isinstance(values[2], str) and (values[2] == '' or
                     (values[2].isascii() and values[2].isdigit() and len(values[2]) <= 19)))
    except ValueError:
        valid = False
    if not valid:
        _invalid('Reprise incompatible avec l’analyse, l’ancre, le sens ou la priorité.')
    return values[1], values[2]


def _arguments(exchange, arguments):
    if set(arguments) - _FIELDS:
        _invalid('Argument de voisinage inconnu.')
    if arguments.get('analysis') != exchange.scan.id:
        _invalid('analysis doit identifier l’analyse de cet échange (describe).')
    root = arguments.get('root')
    if not isinstance(root, str) or len(root) > 1000 or not is_reference(root):
        _invalid('root doit être une référence du contrat.')
    exchange._own(root)
    relations = _relations(arguments.get('follow'))
    priority = arguments.get('priority', relations)
    if (not isinstance(priority, list) or any(not isinstance(item, str) for item in priority)
            or len(priority) != len(relations) or set(priority) != set(relations)):
        _invalid('priority doit ordonner exactement les relations de follow.')
    direction = arguments.get('direction')
    if direction not in ('INCOMING', 'OUTGOING'):
        _invalid('direction : INCOMING ou OUTGOING.')
    # Deliberate first slice: do not silently treat a deeper request as one hop.
    depth = _integer(arguments, 'depth', 1, 1)
    limits = {name: _integer(arguments, name, default, maximum) for name, default, maximum in
              (('max_nodes', 30, 200), ('max_edges', 60, 200), ('max_work', 100, 1000))}
    parameters = {'root': root, 'follow': relations, 'priority': priority, 'direction': direction,
                  'depth': depth}
    return parameters, limits


def _coverage(exchange, root, relations, priority):
    coverage, frontier, capabilities = _summaries(exchange, relations)
    for relation in priority:
        if relation not in capabilities:
            frontier.append({'nature': 'CONTEXT', 'node': root, 'relation': relation,
                             'reason': 'NO_ANALYZER', 'count': {'kind': 'UNKNOWN'}})
    frontier += _unread_languages(exchange, [relation for relation in priority if relation in capabilities])
    return coverage, frontier, capabilities


def _summaries(exchange, relations):
    """Ce que le resume de l'analyse dit des analyseurs des relations suivies : leur couverture, leurs
    lacunes, et les relations qu'ils rendent disponibles."""
    coverage, frontier, capabilities = [], [], set()
    for evaluation in exchange.evaluations:
        identifier = evaluation['evaluator_id']
        produced = exchange.service.catalogs.get(identifier, frozenset(evaluation.get('relations', {})))
        if not set(relations).intersection(produced):
            continue
        # TAXO-COV-01 : un analyseur qui n'avait rien a lire n'est pas une capacite de cette analyse.
        if evaluation['status'] != 'UNSUPPORTED':
            capabilities.update(produced)
        coverage.append({'producer': identifier, 'scope': 'ANALYSIS_SUMMARY',
                         'status': evaluation['status'], 'coverage': evaluation.get('coverage', [])})
        gaps = [item for item in evaluation.get('coverage', [])
                if item[_TYPE] in ('NOT_INTERPRETED', 'READ_ERROR')]
        if evaluation['status'] in ('FAILED', 'PARTIAL') or gaps:
            frontier.append(_knowledge('ANALYSIS_INCOMPLETE', producer=identifier))
    return coverage, frontier, capabilities


def _unread_languages(exchange, relations):
    """Les langages presents qu'aucune execution capable n'a lus, relation par relation : ce qui s'y trouve
    est inconnu (TAXO-COV-01). Lus dans le resume de l'analyse, sans parcourir ses faits ; une analyse
    anterieure a TAXO-COV-01 les relit dans ses faits ; sans resume d'inventaire, rien n'en est dit."""
    result = exchange.scan.result
    present = result.get('languages')
    if present is None and 'evaluation_summary' in result:
        # Une analyse anterieure a TAXO-COV-01 : ses langages sont relus dans ses faits, comme pour les verdicts.
        present = exchange.languages
    if present is None:
        return []
    summarized = _summarized(exchange)
    complete = languages_complete(exchange.scan.result.get('evaluation_summary'))
    frontier = []
    for relation in relations:
        unread = not_analysed(summarized, relation, present)
        if unread:
            frontier.append(_knowledge('NOT_ANALYSED', relation=relation, languages=list(unread)))
        if unknown_languages(summarized, relation, present, complete):
            frontier.append(_knowledge('LANGUAGES_UNKNOWN', relation=relation))
    return frontier


def _knowledge(reason, **fields):
    """Une frontiere de connaissance : ce que seule une capacite d'analyse amelioree ferait connaitre."""
    return {'nature': 'KNOWLEDGE', 'scope': 'ANALYSIS', **fields, 'reason': reason, 'count': {'kind': 'UNKNOWN'}}


def _summarized(exchange):
    """Les analyseurs tels que le resume de l'analyse les decrit : statut, relations, couvertures et
    langages de leur contrat de catalogue (TAXO-COV-01)."""
    found, recorded = [], None
    for evaluation in exchange.evaluations:
        identifier = evaluation['evaluator_id']
        relations = exchange.service.catalogs.get(identifier, frozenset(evaluation.get('relations', {})))
        # Le resume ne garde que les types de couverture : assez pour savoir si l'execution a analyse.
        coverage = tuple({_TYPE: item[_TYPE]} for item in evaluation.get('coverage', []))
        if evaluation.get('catalog_id') is None and recorded is None:
            recorded = _recorded_contracts(exchange)
        reads = (recorded.get(identifier, Reads.unknown()) if evaluation.get('catalog_id') is None
                 else exchange.service.reads_of(evaluation))
        found.append(Analyzer(identifier, relations, evaluation['status'] == 'FAILED', coverage, reads,
                              evaluation['status'] == 'UNSUPPORTED'))
    return found


def _recorded_contracts(exchange):
    """Un resume anterieur a TAXO-COV-01 ne nomme pas son catalogue : chaque execution est lue selon le contrat
    enregistre avec elle, celui que portent ses couvertures et que lisent les verdicts, jamais selon le
    catalogue actuel de son analyseur. Une lecture bornee : une ligne par execution, aucun fait. Sans
    execution enregistree, son contrat est inconnu : il ne lit rien de connu. Une analyse n'a qu'une execution
    par evaluateur (par construction, pas par la base) ; si plusieurs executions d'un producteur nommaient des
    contrats differents, aucun ne serait choisi a la place des autres : le contrat serait inconnu."""
    found = {}
    for execution in exchange.service.facts.executions(exchange.scan.id):
        if execution.producer_type != 'EVALUATOR':
            continue
        reads = exchange.service.reads_of(vars(execution))
        known = found.get(execution.producer_id, reads)
        found[execution.producer_id] = reads if known == reads else Reads.unknown()
    return found


class _Neighborhood:
    """Selection state for one page; rendering never advances the cursor."""

    def __init__(self, exchange, parameters, limits, token, max_bytes):
        self.exchange = exchange
        self.parameters = parameters
        self.limits = limits
        self.max_bytes = max_bytes
        self.root = parameters['root']
        self.priority = parameters['priority']
        self.direction = parameters['direction']
        self.store = exchange.service.facts
        self.revision = self.store.revision(exchange.scan.id)
        self.binding = hashlib.sha256(json.dumps(
            [VERSION, exchange.snapshot, parameters, self.revision], sort_keys=True).encode()).hexdigest()
        self.position, self.after = _resume(token, self.binding, len(self.priority))
        self.nodes, self.selected, self.refs, self.work = [self.root], [], [], 0
        self.known = self.store.has_reference(exchange.scan.id, self.root)
        self.coverage, self.frontier, self.capabilities = _coverage(
            exchange, self.root, parameters['follow'], self.priority)

    def render(self, reason, *, position=None, key=None, found=False):
        position = self.position if position is None else position
        key = self.after if key is None else key
        boundaries = list(self.frontier)
        for node in self.nodes[1:]:
            boundaries.append({'nature': 'SELECTION', 'node': node, 'reason': 'DEPTH',
                               'count': {'kind': 'UNKNOWN'}})
        continuation = None
        if position < len(self.priority) and reason != 'ROOT_UNKNOWN':
            continuation = _cursor(self.binding, position, key)
            boundaries.append({'nature': 'SELECTION', 'node': self.root, 'relation': self.priority[position],
                               'reason': reason, 'count': ({'kind': 'AT_LEAST', 'value': 1} if found
                                                          else {'kind': 'UNKNOWN'}),
                               'continuation': continuation})
        response = Response('get_neighborhood', self.exchange.snapshot, self.coverage, self.max_bytes,
                            engine_version=VERSION, parameters=self.parameters, facts_revision=self.revision,
                            bounds={**self.limits, 'max_bytes': self.max_bytes},
                            consumed={'nodes': len(self.nodes), 'edges': len(self.selected), 'work': self.work},
                            anchor={'reference': self.root, 'known': self.known}, nodes=list(self.nodes),
                            frontier=boundaries, stop_reason=reason, continuation=continuation)
        response.envelope['items'] = list(self.selected)
        return response

    def fits(self, response):
        return size(response.close()) <= self.max_bytes

    def _accept(self, key, fact):
        # The index projects persisted assertions; it never invents a relation.
        neighbor = fact.get('object') if self.direction == 'OUTGOING' else fact['subject']
        new_node = isinstance(neighbor, str) and is_reference(neighbor) and neighbor not in self.nodes
        if new_node and len(self.nodes) == self.limits['max_nodes']:
            return self.render('NODES', found=True)
        ref, created = self.exchange.refs.fact(fact)
        self.selected.append({'ref': ref, 'fact': {k: v for k, v in fact.items() if k != 'evidence'},
                              'evidence_count': len(fact.get('evidence', []))})
        if new_node:
            self.nodes.append(neighbor)
        if not self.fits(self.render('BYTES', key=key)):
            self.selected.pop()
            if new_node:
                self.nodes.pop()
            if created:
                self.exchange.refs.forget(ref)
            return self.render('BYTES', found=True)
        if created:
            self.refs.append(ref)
        self.after = key
        return None

    def _next_relation(self):
        self.position += 1
        self.after = ''

    def _walk(self):
        while self.position < len(self.priority):
            if self.work >= self.limits['max_work']:
                return self.render('WORK')
            if len(self.selected) >= self.limits['max_edges']:
                return self.render('EDGES')
            relation = self.priority[self.position]
            if relation not in self.capabilities:
                self._next_relation()
                continue
            self.work += 1  # Empty adjacency lookups consume work as well.
            adjacent = self.store.neighbor(self.exchange.scan.id, self.root, relation, self.direction, self.after)
            if adjacent is None:
                self._next_relation()
                continue
            stopped = self._accept(*adjacent)
            if stopped is not None:
                return stopped
        return self.render('ADJACENCY_COMPLETE')

    def _forget_refs(self):
        for ref in reversed(self.refs):
            self.exchange.refs.forget(ref)

    def run(self):
        if not self.known:
            result = self.render('ROOT_UNKNOWN', position=len(self.priority), key='')
        else:
            if not self.fits(self.render('WORK')):
                raise OperationError(BUDGET_EXHAUSTED, 'Le budget ne contient pas l’enveloppe et sa frontière.')
            result = self._walk()
        if self.store.revision(self.exchange.scan.id) != self.revision:
            self._forget_refs()
            _invalid('Les faits de cette analyse ont changé pendant le parcours ; recommencer sans reprise.')
        if not self.fits(result):
            self._forget_refs()
            raise OperationError(BUDGET_EXHAUSTED, 'Le budget ne contient pas la réponse et sa frontière.')
        return result


def neighborhood(exchange, arguments, max_bytes):
    parameters, limits = _arguments(exchange, arguments)
    return _Neighborhood(exchange, parameters, limits, arguments.get('continuation'), max_bytes).run()
