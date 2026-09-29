"""First explicit tile: bounded, indexed one-hop selection over persisted facts.

No parser, repository reader, model or implicit reverse relation. Coverage summaries are
labelled as analysis-wide: they cannot establish the absence of a runtime relationship.
"""
import base64
import hashlib
import json

from app.facts import is_reference
from app.facts.domain.fact import RELATIONS
from app.protocol.domain.envelope import (BUDGET_EXHAUSTED, INVALID_ARGUMENT,
                                          OperationError, Response, size)

VERSION = 'neighborhood/1'
_FIELDS = {'analysis', 'root', 'follow', 'direction', 'depth', 'priority', 'max_nodes', 'max_edges',
           'max_work', 'continuation'}


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
                 and isinstance(values[2], str) and len(values[2]) <= 10000)
    except (ValueError, UnicodeError):
        valid = False
    if not valid:
        _invalid('Reprise incompatible avec l’analyse, l’ancre, le sens ou la priorité.')
    return values[1], values[2]


def neighborhood(exchange, arguments, max_bytes):
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
    binding = hashlib.sha256(json.dumps([VERSION, exchange.snapshot, parameters], sort_keys=True).encode()).hexdigest()
    position, after = _resume(arguments.get('continuation'), binding, len(priority))
    store = exchange.service.facts
    nodes, selected, refs, work = [root], [], [], 0
    known = store.has_reference(exchange.scan.id, root)
    coverage, frontier = [], []
    capabilities = set()
    for evaluation in exchange.evaluations:
        identifier = evaluation['evaluator_id']
        produced = exchange.service.catalogs.get(identifier, frozenset(evaluation.get('relations', {})))
        if not set(relations).intersection(produced):
            continue
        capabilities.update(produced)
        coverage.append({'producer': identifier, 'scope': 'ANALYSIS_SUMMARY',
                         'status': evaluation['status'], 'coverage': evaluation.get('coverage', [])})
        gaps = [item for item in evaluation.get('coverage', [])
                if item['coverage_type'] in ('NOT_INTERPRETED', 'READ_ERROR')]
        if evaluation['status'] in ('FAILED', 'PARTIAL') or gaps:
            frontier.append({'nature': 'KNOWLEDGE', 'scope': 'ANALYSIS', 'producer': identifier,
                             'reason': 'ANALYSIS_INCOMPLETE', 'count': {'kind': 'UNKNOWN'}})
    for relation in priority:
        if relation not in capabilities:
            frontier.append({'nature': 'CONTEXT', 'node': root, 'relation': relation,
                             'reason': 'NO_ANALYZER', 'count': {'kind': 'UNKNOWN'}})

    def render(reason, pos, key, found=False):
        boundaries = list(frontier)
        for node in nodes[1:]:
            boundaries.append({'nature': 'SELECTION', 'node': node, 'reason': 'DEPTH',
                               'count': {'kind': 'UNKNOWN'}})
        continuation = None
        if pos < len(priority) and reason != 'ROOT_UNKNOWN':
            continuation = _cursor(binding, pos, key)
            boundaries.append({'nature': 'SELECTION', 'node': root, 'relation': priority[pos],
                               'reason': reason, 'count': ({'kind': 'AT_LEAST', 'value': 1} if found
                                                          else {'kind': 'UNKNOWN'}),
                               'continuation': continuation})
        response = Response('get_neighborhood', exchange.snapshot, coverage, max_bytes,
                            engine_version=VERSION, parameters=parameters,
                            bounds={**limits, 'max_bytes': max_bytes},
                            consumed={'nodes': len(nodes), 'edges': len(selected), 'work': work},
                            anchor={'reference': root, 'known': known}, nodes=list(nodes),
                            frontier=boundaries, stop_reason=reason, continuation=continuation)
        response.envelope['items'] = list(selected)
        return response

    def fits(response):
        return size(response.close()) <= max_bytes

    if not known:
        result = render('ROOT_UNKNOWN', len(priority), '')
    else:
        result = render('WORK', position, after)
        if not fits(result):
            raise OperationError(BUDGET_EXHAUSTED, 'Le budget ne contient pas l’enveloppe et sa frontière.')
        while position < len(priority):
            if work >= limits['max_work']:
                result = render('WORK', position, after)
                break
            if len(selected) >= limits['max_edges']:
                result = render('EDGES', position, after)
                break
            relation = priority[position]
            if relation not in capabilities:
                position, after = position + 1, ''
                continue
            work += 1  # Includes empty lookups: the work cap bounds database requests, too.
            adjacent = store.neighbor(exchange.scan.id, root, relation, direction, after)
            if adjacent is None:
                position, after = position + 1, ''
                result = render('ADJACENCY_COMPLETE', position, after)
                continue
            key, fact = adjacent
            # The index is a projection of persisted assertions, never a source of new facts.
            neighbor = fact.get('object') if direction == 'OUTGOING' else fact['subject']
            new_node = is_reference(neighbor) if isinstance(neighbor, str) else False
            new_node = new_node and neighbor not in nodes
            if new_node and len(nodes) == limits['max_nodes']:
                result = render('NODES', position, after, True)
                break
            ref, created = exchange.refs.fact(fact)
            selected.append({'ref': ref, 'fact': {k: v for k, v in fact.items() if k != 'evidence'},
                             'evidence_count': len(fact.get('evidence', []))})
            if new_node:
                nodes.append(neighbor)
            candidate = render('BYTES', position, key)
            if not fits(candidate):
                selected.pop()
                if new_node:
                    nodes.pop()
                if created:
                    exchange.refs.forget(ref)
                result = render('BYTES', position, after, True)
                break
            if created:
                refs.append(ref)
            after = key
            result = candidate
        else:
            result = render('ADJACENCY_COMPLETE', position, after)
    if not fits(result):
        for ref in reversed(refs):
            exchange.refs.forget(ref)
        raise OperationError(BUDGET_EXHAUSTED, 'Le budget ne contient pas la réponse et sa frontière.')
    return result
