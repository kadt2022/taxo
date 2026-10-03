"""Lire une demande de voisinage du protocole et choisir sa version (TAXO-01J, § 8).

Sans `engine`, une demande est servie par `neighborhood/1` si et seulement si elle y est valide exactement
(ses arguments, ses valeurs, ses plafonds, une reprise qu'il a émise) ; toute autre demande relève de
`neighborhood/2`. Une reprise d'une version n'est jamais acceptée par l'autre.
"""
from dataclasses import dataclass

from app.facts import is_reference
from app.facts.domain.fact import RELATIONS
from app.neighborhood.domain.continuation import V1, V2, is_v2
from app.neighborhood.domain.request import DIRECTIONS, INCOMING, OUTGOING, Limits, Step, TileRequest
from app.protocol.application.neighborhood_form import FORMS, FULL
from app.protocol.domain.envelope import INVALID_ARGUMENT, OperationError

BOTH = 'BOTH'
_V1_FIELDS = frozenset({'analysis', 'root', 'follow', 'direction', 'depth', 'priority', 'max_nodes', 'max_edges',
                        'max_work', 'continuation'})
_V2_FIELDS = _V1_FIELDS | {'engine', 'steps', 'max_fanout', 'evidence', 'form'}
NONE, SUMMARY = 'NONE', 'SUMMARY'
# (défaut, plafond) de chaque budget, par version.
_LIMITS = {V1: {'max_nodes': (30, 200), 'max_edges': (60, 200), 'max_work': (100, 1000)},
           V2: {'max_nodes': (30, 200), 'max_edges': (60, 400), 'max_work': (100, 2000)}}
_DEPTH = {V1: 1, V2: 4}
MAX_FANOUT = 200
MAX_STEPS = 16


@dataclass(frozen=True)
class NeighborhoodDemand:
    """Une demande lue : la Tuile à construire, et ce qui ne regarde que sa présentation (les preuves résumées
    s'ajoutent à une sélection déjà fixée, la forme compacte la représente : ni l'une ni l'autre ne la change)."""
    version: str
    request: TileRequest
    parameters: dict
    continuation: str | None
    evidence: str = NONE
    form: str = FULL


def _invalid(message):
    raise OperationError(INVALID_ARGUMENT, message)


def _integer(arguments, name, default, maximum):
    value = arguments.get(name, default)
    if type(value) is not int or not 1 <= value <= maximum:
        _invalid(f'{name} doit être un entier entre 1 et {maximum}.')
    return value


def _relations(value):
    if (not isinstance(value, list) or not 1 <= len(value) <= MAX_STEPS
            or any(not isinstance(item, str) or item not in RELATIONS for item in value)
            or len(set(value)) != len(value)):
        _invalid('follow : 1 à 16 relations distinctes du vocabulaire.')
    return value


def _anchor(exchange, arguments, fields):
    if set(arguments) - fields:
        _invalid('Argument de voisinage inconnu.')
    if arguments.get('analysis') != exchange.scan.id:
        _invalid('analysis doit identifier l’analyse de cet échange (describe).')
    root = arguments.get('root')
    if not isinstance(root, str) or len(root) > 1000 or not is_reference(root):
        _invalid('root doit être une référence du contrat.')
    exchange.own(root)
    return root


def _priority(arguments, relations):
    priority = arguments.get('priority', relations)
    if (not isinstance(priority, list) or any(not isinstance(item, str) for item in priority)
            or len(priority) != len(relations) or set(priority) != set(relations)):
        _invalid('priority doit ordonner exactement les relations de follow.')
    return priority


def _limits(arguments, version):
    return Limits(**{name: _integer(arguments, name, default, maximum)
                     for name, (default, maximum) in _LIMITS[version].items()})


def _v1(exchange, arguments):
    root = _anchor(exchange, arguments, _V1_FIELDS)
    relations = _relations(arguments.get('follow'))
    priority = _priority(arguments, relations)
    direction = arguments.get('direction')
    if direction not in DIRECTIONS:
        _invalid('direction : INCOMING ou OUTGOING.')
    depth = _integer(arguments, 'depth', 1, 1)
    limits = _limits(arguments, V1)
    request = TileRequest(root, tuple(Step(relation, direction) for relation in priority), depth, limits,
                          batched=False)
    parameters = {'root': root, 'follow': relations, 'priority': priority, 'direction': direction, 'depth': depth}
    return NeighborhoodDemand(V1, request, parameters, arguments.get('continuation'))


def _steps(value):
    if not isinstance(value, list) or not 1 <= len(value) <= MAX_STEPS:
        _invalid('steps : 1 à 16 pas.')
    steps = []
    for item in value:
        if (not isinstance(item, dict) or set(item) != {'relation', 'direction'}
                or not isinstance(item['relation'], str) or item['relation'] not in RELATIONS
                or item['direction'] not in DIRECTIONS):
            _invalid('steps : chaque pas est {"relation": relation du vocabulaire, "direction": INCOMING ou OUTGOING}.')
        steps.append(Step(item['relation'], item['direction']))
    if len(set(steps)) != len(steps):
        _invalid('steps : chaque pas une seule fois.')
    return tuple(steps)


def _followed(arguments):
    """Le raccourci `follow` + `direction` : `BOTH` suit chaque relation en sortant, puis en entrant."""
    relations = _relations(arguments.get('follow'))
    priority = _priority(arguments, relations)
    direction = arguments.get('direction')
    if direction not in (*DIRECTIONS, BOTH):
        _invalid('direction : INCOMING, OUTGOING ou BOTH.')
    directions = (OUTGOING, INCOMING) if direction == BOTH else (direction,)
    return tuple(Step(relation, side) for relation in priority for side in directions)


def _v2(exchange, arguments):
    root = _anchor(exchange, arguments, _V2_FIELDS)
    if 'steps' in arguments:
        if {'follow', 'direction', 'priority'} & set(arguments):
            _invalid('steps exclut follow, direction et priority.')
        steps = _steps(arguments['steps'])
    else:
        steps = _followed(arguments)
    depth = _integer(arguments, 'depth', 1, _DEPTH[V2])
    limits = _limits(arguments, V2)
    fanout = arguments.get('max_fanout')
    if fanout is not None:
        fanout = _integer(arguments, 'max_fanout', None, MAX_FANOUT)
    evidence = arguments.get('evidence', NONE)
    if evidence not in (NONE, SUMMARY):
        _invalid('evidence : NONE ou SUMMARY.')
    form = arguments.get('form', FULL)
    if form not in FORMS:
        _invalid('form : FULL ou COMPACT.')
    request = TileRequest(root, steps, depth, limits, fanout)
    parameters = {'root': root, 'steps': [{'relation': step.relation, 'direction': step.direction} for step in steps],
                  'depth': depth, 'max_fanout': fanout, 'evidence': evidence, 'form': form}
    return NeighborhoodDemand(V2, request, parameters, arguments.get('continuation'), evidence, form)


def _accepted_by_v1(exchange, arguments):
    try:
        _v1(exchange, arguments)
    except OperationError:
        return False
    return True


def read_demand(exchange, arguments) -> NeighborhoodDemand:
    """La demande, lue selon sa version : `engine` s'il est donné ; sinon une reprise de `neighborhood/2` ; sinon
    `neighborhood/1` si elle y est valide exactement, et `neighborhood/2` dans tous les autres cas."""
    engine = arguments.get('engine')
    if engine is not None and engine not in (V1, V2):
        _invalid('engine : neighborhood/1 ou neighborhood/2.')
    if engine == V1:
        return _v1(exchange, {key: value for key, value in arguments.items() if key != 'engine'})
    if engine is None and not is_v2(arguments.get('continuation')) and _accepted_by_v1(exchange, arguments):
        return _v1(exchange, arguments)
    return _v2(exchange, arguments)
