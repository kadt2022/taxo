"""Le chemin d'une route et ses tuiles de méthode (essai A/B du 2026-10-15, validé par le Capitaine Pi).

Taxo connaît le chemin ; Minia le sert, le LLM raisonne. Depuis une route (ou une méthode), le chemin suit les faits de
la Maille : `HANDLED_BY`, puis `CALLS` jusqu'à `DEPTH` niveaux et `MAX_METHODS` méthodes, et la méthode de la chaîne de
filtres que nomme `MATCHED_BY` (`filter_chain`), avec la règle d'URL écrite. Rien n'est deviné : une méthode que la
Maille ne relie pas n'est pas sur le chemin, et ses frontières (appels non interprétés) sont dites.

Chaque méthode est numérotée sur une carte. Sa **tuile** : l'en-tête de sa classe (annotations et déclaration), la
méthode complète telle qu'écrite (annotations et variables locales comprises), la déclaration des champs qu'elle utilise
et l'en-tête des types du projet dont elle dépend. Le code passe par `get_source`, sous son consentement, ses refus et sa
classification ; une classe ou un type déjà donné dans l'échange n'est pas redonné.

Types joints : `RESOLVED` quand Taxo les relie (type d'un champ utilisé, `uses`) ; `NAMED` quand le nom est écrit dans
le code de la méthode et désigne un seul type du projet (une limite dite : ce n'est pas une résolution de compilateur ;
un nom porté par deux types n'est jamais rattaché).

Deux modes (`MINIA_PATH_MODE`) :
- `full` (A) : la carte et toutes les tuiles qui tiennent dans le budget, en une réponse ;
- `map` (B) : la carte et la tuile d'entrée ; le modèle demande ensuite les tuiles par numéro (`read_tiles`), en lot.

Le chemin et chaque lecture de tuiles comptent chacun pour **une** opération de l'échange, de la taille de ce qui est
rendu ; ce qui ne tient pas, ou n'est pas lisible, est dit dans `not_sent`, jamais tu.
"""
import re

from app.minia.application import sources
from app.protocol.domain.envelope import error, size

OPERATION, READ = 'get_path', 'read_tiles'
OFF, FULL, MAP = 'off', 'full', 'map'
MODES = (OFF, FULL, MAP)
DEPTH, MAX_METHODS = 4, 30
MAX_PATH_BYTES = 24_000
PIECE_BYTES = 16_000
MAX_NOT_FOLLOWED = 20
_INVALID = 'INVALID_ARGUMENT'
_NOTE = {
    FULL: 'Le chemin calculé par Taxo depuis la référence, et le code de chaque méthode (tuile). Une tuile non transmise '
          '(budget) se lit avec read_tiles(numbers). Les frontières disent où le graphe s’arrête.',
    MAP: 'La carte numérotée du chemin calculé par Taxo et la tuile d’entrée. Demande en une fois les tuiles dont tu as '
         'besoin : read_tiles(numbers=[2, 4]). Les frontières disent où le graphe s’arrête.',
}


def offered():
    """Les deux opérations, telles que le modèle les voit."""
    return [{'kind': 'operation', 'operation': OPERATION,
             'arguments': {'reference': 'une route (endpoint:…) ou une méthode (symbol:…) reçue de Taxo'},
             'note': 'Le chemin de la Maille depuis cette référence : carte numérotée et code des méthodes.'},
            {'kind': 'operation', 'operation': READ, 'arguments': {'numbers': 'numéros de la carte, ex. [2, 4]'},
             'note': 'Le code des méthodes de la carte, en une fois, sans recherche.'}]


# --- Le chemin ----------------------------------------------------------------------------------------------------

def _facts(exchange, **query):
    return [fact for fact in exchange.query(kind='ASSERTION', **query) if fact.get('validity', 'VALID') == 'VALID']


def _short(reference):
    key = reference.removeprefix('symbol:java:')
    owner, _, member = key.partition('#')
    name = owner.rsplit('.', 1)[-1]
    return f'{name}.{member}' if member else name


def walk(exchange, reference):
    """Les méthodes du chemin dans l'ordre (largeur d'abord), leurs appels, la chaîne de filtres et les règles d'URL,
    et les appels connus non suivis (bornes)."""
    route = reference.startswith('endpoint:')
    starts = sorted(fact['object'] for fact in _facts(exchange, subject=reference, relation='HANDLED_BY')) \
        if route else [reference]
    matched = _facts(exchange, subject=reference, relation='MATCHED_BY') if route else []
    chains = sorted({fact.get('qualifiers', {}).get('filter_chain') for fact in matched} - {None})
    order, calls, seen, beyond = [], {}, set(), []
    queue = [(start, 0) for start in starts]
    while queue:
        method, level = queue.pop(0)
        if method in seen:
            continue
        if len(order) >= MAX_METHODS:
            beyond.append(method)
            continue
        seen.add(method)
        order.append(method)
        calls[method] = sorted({fact['object'] for fact in _facts(exchange, subject=method, relation='CALLS')})
        for callee in calls[method]:
            if level < DEPTH:
                queue.append((callee, level + 1))
            elif callee not in seen:
                beyond.append(callee)
    for chain in chains:
        if chain not in seen and len(order) < MAX_METHODS:
            order.append(chain)
            calls.setdefault(chain, [])
    rules = []
    for fact in matched:
        chain = fact.get('qualifiers', {}).get('filter_chain')
        written = [f'{rule["relation"]} {rule.get("object", "")}'.strip()
                   for rule in _facts(exchange, subject=fact['object'])
                   if rule['relation'] in ('AUTHORIZED_BY', 'PERMITS_ALL')
                   and rule.get('qualifiers', {}).get('filter_chain') == chain]
        rules.append({'pattern': fact['object'], 'filter_chain': chain, 'rules': written})
    beyond = sorted(set(beyond) - seen)
    return order, calls, chains, rules, beyond


def _frontier(exchange, method):
    return sorted({fact.get('reason') or fact.get('coverage_type') for fact in exchange.query(kind='COVERAGE', subject=method)
                   if fact.get('coverage_type') in ('NOT_INTERPRETED', 'NOT_ANALYSED')})


# --- Les tuiles ----------------------------------------------------------------------------------------------------

def _piece(exchange, reference):
    """Le code d'un symbole par `get_source` de l'échange (consentement, refus, classification) ; sinon la raison."""
    try:
        response = exchange.get_source({'reference': reference}, PIECE_BYTES).close()
    except Exception as exc:  # noqa: BLE001 - un refus du protocole (consentement, référence) devient une raison dite
        return None, getattr(exc, 'code', 'NOT_AVAILABLE')
    if response.get('outcome') != 'OK' or not response.get('items'):
        reasons = [item.get('reason') for item in response.get('not_sent') or () if item.get('reason')]
        return None, (reasons[0] if reasons else 'NOT_AVAILABLE')
    return response, None


def _header(exchange, reference, headers):
    """L'en-tête d'un type : ses annotations et sa déclaration, jusqu'à la première accolade."""
    if reference not in headers:
        response, _ = _piece(exchange, reference)
        if response is None:
            headers[reference] = None
        else:
            item = response['items'][0]
            lines, kept = item['text'].splitlines(), []
            for line in lines:
                kept.append(line)
                if '{' in line and not line.lstrip().startswith('@'):
                    break
            rest = lines[len(kept):]
            closing = '\n    …\n}' if any(line.strip() not in ('', '}') for line in rest) else ('\n}' if rest else '')
            headers[reference] = {'reference': reference, 'path': item['path'], 'line_start': item['line_start'],
                                  'text': '\n'.join(kept) + closing}
    return headers[reference]


def _project_types(exchange):
    """Les types déclarés du projet, par nom simple ; un nom porté par deux types n'est rattaché à aucun."""
    by_name = {}
    for fact in _facts(exchange, relation='CONTAINS'):
        reference = fact['object']
        if reference.startswith('symbol:') and '#' not in reference:
            by_name.setdefault(_short(reference), set()).add(reference)
    return {name: next(iter(found)) for name, found in by_name.items() if len(found) == 1}


def _tile(exchange, number, method, context, given):
    """La tuile d'une méthode : sa classe, son code, ses champs et ses types, sans redonner ce qui l'a déjà été."""
    response, reason = _piece(exchange, method)
    if response is None:
        return None, reason
    item = response['items'][0]
    owner = method.split('#', 1)[0]
    fields = [entry['text'].strip() for entry in response.get('field_context') or () if entry.get('text')]
    resolved = {use['reference'] for use in response.get('uses') or ()
                if '#' not in use['reference'] and use['reference'] != owner}
    names = set(re.findall(r'\b([A-Z][A-Za-z0-9_]*)\b', item['text'] + '\n' + '\n'.join(fields)))
    named = {context['types'][name] for name in names if name in context['types']} - resolved - {owner}
    tile = {'number': number, 'reference': method, 'path': item['path'], 'line_start': item['line_start'],
            'line_end': item['line_end'], 'truncated': item.get('truncated', False), 'fields': fields,
            'code': item['text']}
    if owner not in given:
        header = _header(exchange, owner, context['headers'])
        if header:
            tile['class'] = header
        given.add(owner)
    types = []
    for reference, resolution in [*((ref, 'RESOLVED') for ref in sorted(resolved)),
                                  *((ref, 'NAMED') for ref in sorted(named))]:
        if reference in given:
            continue
        header = _header(exchange, reference, context['headers'])
        if header:
            types.append({**header, 'resolution': resolution})
            given.add(reference)
    if types:
        tile['types'] = types
    return tile, None


def _given(exchanged):
    """Les classes et types déjà donnés par un chemin ou une lecture de tuiles de l'échange."""
    given = set()
    for item in exchanged:
        if item.get('operation') in (OPERATION, READ):
            for tile in item['response'].get('tiles') or ():
                given.add(tile['reference'].split('#', 1)[0])
                given.update(entry['reference'] for entry in tile.get('types') or ())
    return given


def _fill(exchange, response, numbered, wanted, given, max_bytes):
    """Ajoute les tuiles voulues, dans l'ordre, tant qu'elles tiennent ; le reste est dit dans `not_sent`."""
    context = {'headers': {}, 'types': _project_types(exchange)}
    missing = {}
    for number in wanted:
        tile, reason = _tile(exchange, number, numbered[number], context, given)
        if tile is None:
            missing.setdefault(reason, []).append(number)
            continue
        response['tiles'].append(tile)
        if size(response) > max_bytes:
            response['tiles'].pop()
            missing.setdefault('BUDGET', []).append(number)
    for reason, numbers in missing.items():
        response['not_sent'].append({'what': 'tiles', 'numbers': numbers, 'reason': reason})


def _sized(response):
    sized = {**response, 'bytes': 0}
    while sized['bytes'] != size(sized):
        sized['bytes'] = size(sized)
    return sized


def _path(exchange, reference, mode, max_bytes, exchanged):
    order, calls, chains, rules, beyond = walk(exchange, reference)
    if not order:
        return error(OPERATION, exchange.snapshot, _INVALID,
                     'reference : aucune méthode de la Maille ne traite cette route (HANDLED_BY), ou ce n’est pas une '
                     'méthode.')
    numbered = dict(enumerate(order, 1))
    number = {method: index for index, method in numbered.items()}
    carte = []
    for index, method in numbered.items():
        entry = {'number': index, 'reference': method, 'name': _short(method),
                 'calls': [number.get(callee, callee) for callee in calls.get(method, [])]}
        if method in chains:
            entry['role'] = 'filter_chain'
        frontier = _frontier(exchange, method)
        if frontier:
            entry['frontier'] = frontier
        carte.append(entry)
    response = {'operation': OPERATION, 'outcome': 'OK', 'snapshot': exchange.snapshot, 'reference': reference,
                'mode': mode, 'note': _NOTE[mode], 'map': carte, 'rules': rules, 'tiles': [], 'not_sent': [],
                'bounds': {'depth': DEPTH, 'max_methods': MAX_METHODS}}
    if beyond:
        response['not_followed'] = {'count': len(beyond), 'references': beyond[:MAX_NOT_FOLLOWED]}
    wanted = list(numbered) if mode == FULL else [1]
    if sources.OPERATION not in exchange.available():
        response['not_sent'].append({'what': 'tiles', 'numbers': wanted, 'reason': 'NO_CONSENT'})
    else:
        _fill(exchange, response, numbered, wanted, _given(exchanged), max_bytes)
    if mode == FULL:
        sent = {tile['number'] for tile in response['tiles']}
        missing = [index for index in numbered if index not in sent]
        response['to_read'] = missing
    return response


def _read(exchange, arguments, max_bytes, exchanged):
    numbers = arguments.get('numbers')
    if not isinstance(numbers, list) or not numbers or not all(type(value) is int for value in numbers):
        return error(READ, exchange.snapshot, _INVALID, 'numbers : une liste de numéros de la carte, ex. [2, 4].')
    paths = [item['response'] for item in exchanged
             if item.get('operation') == OPERATION and item['response'].get('outcome') == 'OK']
    if not paths:
        return error(READ, exchange.snapshot, _INVALID, 'Aucune carte reçue dans cet échange : demande d’abord get_path.')
    numbered = {entry['number']: entry['reference'] for entry in paths[-1]['map']}
    unknown = sorted({value for value in numbers if value not in numbered})
    response = {'operation': READ, 'outcome': 'OK', 'snapshot': exchange.snapshot, 'tiles': [], 'not_sent': []}
    if unknown:
        response['not_sent'].append({'what': 'tiles', 'numbers': unknown, 'reason': 'UNKNOWN_NUMBER'})
    wanted = [value for value in dict.fromkeys(numbers) if value in numbered]
    if sources.OPERATION not in exchange.available():
        response['not_sent'].append({'what': 'tiles', 'numbers': wanted, 'reason': 'NO_CONSENT'})
    elif wanted:
        _fill(exchange, response, numbered, wanted, _given(exchanged), max_bytes)
    return response


def request(exchange, step, space, exchanged, mode, trusted=False):
    """Le chemin (`get_path`) ou des tuiles de sa carte (`read_tiles`), comptés chacun comme une opération de l'échange.
    `trusted` : la référence vient de Minia (l'ancre de la question, trouvée par Taxo), pas du modèle."""
    arguments = step.arguments if isinstance(step.arguments, dict) else {}
    requested = MAX_PATH_BYTES if space is None else max(min(space, MAX_PATH_BYTES), 1)

    def serve(max_bytes):
        if step.operation == READ:
            unknown = sorted(set(arguments) - {'numbers'})
            if unknown:
                return _sized(error(READ, exchange.snapshot, _INVALID, f'Argument inconnu : {unknown[0][:100]}.'))
            return _sized(_read(exchange, arguments, max_bytes, exchanged))
        unknown = sorted(set(arguments) - {'reference'})
        reference = arguments.get('reference')
        if unknown or not isinstance(reference, str):
            return _sized(error(OPERATION, exchange.snapshot, _INVALID, 'reference : une route ou une méthode reçue.'))
        if not trusted and not sources.received(reference, exchanged):
            return _sized(error(OPERATION, exchange.snapshot, _INVALID,
                                'reference : une référence reçue de Taxo dans cet échange.'))
        return _sized(_path(exchange, reference, mode, max_bytes, exchanged))
    return exchange.accounted(serve, requested)


def read_owners(exchanged):
    """Les classes dont du code a été lu par une tuile du chemin (pour la garde de conclusion)."""
    return {tile['reference'].split('#', 1)[0] for item in exchanged if item.get('operation') in (OPERATION, READ)
            for tile in item['response'].get('tiles') or ()}
