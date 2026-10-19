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
from app.protocol.domain.source import import_target

OPERATION, READ = 'get_path', 'read_tiles'
OFF, FULL, MAP = 'off', 'full', 'map'
# La cible B (`targeting`) : le LLM désigne sa cible, Minia sert ce chemin (FULL) et ses tuiles, en texte.
TARGET = 'target'
MODES = (OFF, FULL, MAP, TARGET)
EXPLORED = (FULL, MAP)  # les modes où le chemin est une opération de l'exploration classique
DEPTH, MAX_METHODS = 4, 30
MAX_PATH_BYTES = 24_000
PIECE_BYTES = 16_000
MAX_NOT_FOLLOWED = 20
# Les imports d'une tuile (récit contrat de suffisance, lot S3) : ceux dont le nom est utilisé dans la tuile, et les imports avec
# joker. Un import n'est qu'un nom écrit : il identifie le nom complet d'un type, il ne le résout pas.
IMPORTS_SCOPE = {
    'covers': 'imports-named-in-the-tile-and-wildcards/1',
    'note': 'Imports : ceux dont le nom est utilisé dans la tuile, et les imports avec joker (qui ne disent pas quel type est '
            'utilisé). Un type sans import ici est du même paquet, de java.lang, d’un paquet importé avec joker, ou non cité '
            'dans cette tuile.'}
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


# Les règles d'URL écrites pour une chaîne : validées comme elle (producteur, statut, commit, syntaxe), y compris
# l'accès public (`PERMITS_ALL`), que la validation d'ouverture de source ne couvre pas.
_RULE_RELATIONS = frozenset({'AUTHORIZED_BY', 'PERMITS_ALL'})


def walk(exchange, reference):
    """Les méthodes du chemin dans l'ordre (largeur d'abord), leurs appels, la chaîne de filtres et les règles d'URL,
    et les appels connus non suivis (bornes)."""
    route = reference.startswith('endpoint:')
    starts = sorted(fact['object'] for fact in _facts(exchange, subject=reference, relation='HANDLED_BY')) \
        if route else [reference]
    matched = _facts(exchange, subject=reference, relation='MATCHED_BY') if route else []
    # Une chaîne de filtres n'ouvre du code que validée comme partout ailleurs (producteur, statut, commit, syntaxe).
    commit = (exchange.snapshot or {}).get('commit')
    valid = {id(fact): sources.chain_of(fact, commit) for fact in matched}
    chains = sorted(set(valid.values()) - {None})
    order, calls, seen, beyond = _breadth_first(exchange, starts)
    for chain in chains:
        if chain not in seen and len(order) < MAX_METHODS:
            order.append(chain)
            calls.setdefault(chain, [])
    rules = _url_rules(exchange, matched, valid, commit)
    beyond = sorted(set(beyond) - seen)
    return order, calls, chains, rules, beyond


def _breadth_first(exchange, starts):
    """Les méthodes atteintes par `CALLS` depuis `starts`, largeur d'abord, dans les bornes ; et celles laissées
    au-delà."""
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
        if level < DEPTH:
            queue += [(callee, level + 1) for callee in calls[method]]
        else:
            beyond += [callee for callee in calls[method] if callee not in seen]
    return order, calls, seen, beyond


def _url_rules(exchange, matched, valid, commit):
    """Les règles d'URL écrites pour chaque rattachement validé ; un rattachement non validé ne porte aucune règle :
    deux refus ne font pas une correspondance."""
    rules = []
    for fact in matched:
        chain = valid[id(fact)]
        if chain is None:
            continue
        written = [f'{rule["relation"]} {rule.get("object", "")}'.strip()
                   for rule in _facts(exchange, subject=fact['object'])
                   if sources.chain_of(rule, commit, _RULE_RELATIONS) == chain]
        rules.append({'pattern': fact['object'], 'filter_chain': chain, 'rules': written})
    return rules


def _frontier(exchange, method):
    return sorted({fact.get('reason') or fact.get('coverage_type') for fact in exchange.query(kind='COVERAGE', subject=method)
                   if fact.get('coverage_type') in ('NOT_INTERPRETED', 'NOT_ANALYSED')})


# --- Les tuiles ----------------------------------------------------------------------------------------------------

def _piece(exchange, reference):
    """Le code d'un symbole par `get_source` de l'échange (consentement, refus, classification) ; sinon la raison."""
    try:
        response = exchange.get_source({'reference': reference}, PIECE_BYTES).close()
    # Un refus du protocole (consentement, référence) devient une raison dite.
    except Exception as exc:  # noqa: BLE001
        return None, getattr(exc, 'code', 'NOT_AVAILABLE')
    if response.get('outcome') != 'OK' or not response.get('items'):
        reasons = [item.get('reason') for item in response.get('not_sent') or () if item.get('reason')]
        return None, (reasons[0] if reasons else 'NOT_AVAILABLE')
    return response, None


def _header(exchange, reference, headers):
    """L'en-tête d'un type : ses annotations et sa déclaration, jusqu'à la première accolade."""
    if reference not in headers:
        response, _ = _piece(exchange, reference)
        item = response['items'][0] if response is not None else None
        headers[reference] = None if item is None else {
            'reference': reference, 'path': item['path'], 'line_start': item['line_start'], 'text': _head(item['text'])}
    return headers[reference]


def _head(text):
    """Les annotations et la déclaration d'un type, jusqu'à la première accolade ; un corps omis est signalé."""
    lines, kept = text.splitlines(), []
    for line in lines:
        kept.append(line)
        if '{' in line and not line.lstrip().startswith('@'):
            break
    rest = lines[len(kept):]
    if any(line.strip() not in ('', '}') for line in rest):
        return '\n'.join(kept) + '\n    …\n}'
    if rest:
        return '\n'.join(kept) + '\n}'
    return '\n'.join(kept)


def _project_types(exchange):
    """Les types déclarés du projet, par nom simple ; un nom porté par deux types n'est rattaché à aucun."""
    by_name = {}
    for fact in _facts(exchange, relation='CONTAINS'):
        reference = fact['object']
        if reference.startswith('symbol:') and '#' not in reference:
            by_name.setdefault(_short(reference), set()).add(reference)
    return {name: next(iter(found)) for name, found in by_name.items() if len(found) == 1}


def _tile(exchange, number, method, context, given):
    """La tuile d'une méthode : sa classe, son code, ses champs et ses types, sans redonner ce qui l'a déjà été.

    Déduplication transactionnelle : rend aussi les classes et types que la tuile donnerait, sans toucher `given` ; ils
    ne sont tenus pour donnés que si la tuile part. Un en-tête illisible est dit (`unavailable`), jamais tu."""
    response, reason = _piece(exchange, method)
    if response is None:
        return None, reason, set(), []
    item = response['items'][0]
    owner = method.split('#', 1)[0]
    fields = [entry['text'].strip() for entry in response.get('field_context') or () if entry.get('text')]
    resolved = {use['reference'] for use in response.get('uses') or ()
                if '#' not in use['reference'] and use['reference'] != owner}
    names = set(re.findall(r'\b([A-Z]\w*)\b', item['text'] + '\n' + '\n'.join(fields), re.ASCII))
    named = {context['types'][name] for name in names if name in context['types']} - resolved - {owner}
    tile = {'number': number, 'reference': method, 'path': item['path'], 'line_start': item['line_start'],
            'line_end': item['line_end'], 'truncated': item.get('truncated', False), 'fields': fields,
            'code': item['text']}
    adds, unavailable = set(), []
    header = _header(exchange, owner, context['headers'])
    if owner not in given:
        if header:
            tile['class'] = header
            adds.add(owner)
        else:
            unavailable.append(_unavailable('class_header', number, owner))
    shown, why, keys = _imports(exchange, method, '\n'.join([item['text'], *fields, (header or {}).get('text', '')]),
                                item['path'], given | adds)
    if shown:
        tile['imports'] = shown
        adds |= keys
    if why:
        unavailable.append({**_unavailable('imports', number, owner), 'reason': why})
    wanted = [*((ref, 'RESOLVED') for ref in sorted(resolved)), *((ref, 'NAMED') for ref in sorted(named))]
    types = _type_headers(exchange, number, wanted, given, adds, unavailable, context['headers'])
    if types:
        tile['types'] = types
    return tile, None, adds, unavailable


def _import_key(path, entry):
    return f'import:{path}:{entry["line"]}'


def _selected_imports(lines, text):
    """Les imports que la tuile nomme : ceux dont le nom simple est utilisé dans son texte, et les jokers. Jamais une résolution :
    un joker désigne un paquet, pas un type, et il est dit tel."""
    chosen = []
    for entry in lines:
        target = import_target(entry['text'])
        if target is None:
            continue
        name, wildcard = target
        if wildcard:
            chosen.append({**entry, 'wildcard': True})
        elif re.search(rf'(?<![\w$]){re.escape(name.rsplit(".", 1)[-1])}(?![\w$])', text):
            chosen.append(entry)
    return chosen


def _imports(exchange, method, text, path, given):
    """Les imports que la tuile donne, sans redonner ceux déjà donnés pour ce fichier ; sinon la raison de ne pas les lire."""
    try:
        lines = exchange.source_imports(method)
    # Un refus de lecture (consentement, fichier généré ou illisible) devient une raison dite, comme pour le code.
    except Exception as exc:  # noqa: BLE001
        return [], getattr(exc, 'code', 'NOT_AVAILABLE'), set()
    fresh = [entry for entry in _selected_imports(lines, text) if _import_key(path, entry) not in given]
    return fresh, None, {_import_key(path, entry) for entry in fresh}


def _unavailable(what, number, reference):
    return {'what': what, 'number': number, 'reference': reference, 'reason': 'NOT_AVAILABLE'}


def _type_headers(exchange, number, wanted, given, adds, unavailable, headers):
    """Les en-têtes des types que la tuile donnerait (ajoutés à `adds`), sauf ceux déjà donnés ; un en-tête illisible
    est rangé dans `unavailable`."""
    types = []
    for reference, resolution in wanted:
        if reference in given or reference in adds:
            continue
        header = _header(exchange, reference, headers)
        if header:
            types.append({**header, 'resolution': resolution})
            adds.add(reference)
        else:
            unavailable.append(_unavailable('type_header', number, reference))
    return types


def _given(exchanged):
    """Les classes et types déjà donnés par un chemin ou une lecture de tuiles de l'échange."""
    given = set()
    for item in exchanged:
        if item.get('operation') in (OPERATION, READ):
            for tile in item['response'].get('tiles') or ():
                if 'class' in tile:
                    given.add(tile['class']['reference'])
                given.update(_import_key(tile['path'], entry) for entry in tile.get('imports') or ())
                given.update(entry['reference'] for entry in tile.get('types') or ())
    return given


def _fill(exchange, response, numbered, wanted, given, max_bytes, missing):
    """Ajoute les tuiles voulues, dans l'ordre de la carte, tant que la réponse tient ; les autres sont rangées dans
    `missing` par raison. Une tuile refusée ne laisse rien derrière elle : ni classe ni type tenus pour donnés."""
    context = {'headers': {}, 'types': _project_types(exchange)}
    for number in wanted:
        tile, reason, adds, unavailable = _tile(exchange, number, numbered[number], context, given)
        if tile is None:
            missing.setdefault(reason, []).append(number)
            continue
        response['tiles'].append(tile)
        response['not_sent'].extend(unavailable)
        if size(response) > max_bytes:
            response['tiles'].pop()
            del response['not_sent'][len(response['not_sent']) - len(unavailable):]
            missing.setdefault('BUDGET', []).append(number)
            continue
        given |= adds


def _sized(response):
    sized = {**response, 'bytes': 0}
    while sized['bytes'] != size(sized):
        sized['bytes'] = size(sized)
    return sized


def _finish(response, numbered, missing, max_bytes):
    """Dit ce qui manque, puis vérifie la réponse entière (carte, tuiles, signalements) : tant qu'elle dépasse le budget,
    la dernière tuile retenue est retirée et dite. Le chemin incomplet est annoncé en clair."""
    while True:
        shown = {**response, 'not_sent': [*response['not_sent'], *(
            {'what': 'tiles', 'numbers': sorted(numbers), 'reason': reason} for reason, numbers in missing.items())]}
        if 'map' in response:
            _announce(shown, response, numbered, missing)
        if any(tile.get('imports') for tile in response['tiles']):
            shown['imports_scope'] = IMPORTS_SCOPE
        if size(_sized(shown)) <= max_bytes or not response['tiles']:
            return shown
        dropped = response['tiles'].pop()
        response['not_sent'] = [item for item in response['not_sent'] if item.get('number') != dropped['number']]
        missing.setdefault('BUDGET', []).append(dropped['number'])


def _announce(shown, response, numbered, missing):
    """Ce qu'une réponse de chemin dit de sa complétude : `all_tiles_sent` (chaque méthode numérotée a sa tuile, rien
    de plus), les autres limites à part, ce qui reste à lire, et le chemin incomplet en clair."""
    sent = {tile['number'] for tile in response['tiles']}
    absent = [index for index in numbered if index not in sent]
    withheld = {number for numbers in missing.values() for number in numbers}
    shown['all_tiles_sent'] = not absent
    limits = _limits(response)
    if limits:
        shown['limits'] = limits
    if 'NO_CONSENT' not in missing:
        shown['to_read'] = absent
    if not absent:
        return
    said = [f'méthodes {_numbers(index for index in absent if index in withheld)} non transmises '
            '(raison dans not_sent)'] if withheld & set(absent) else []
    rest = [index for index in absent if index not in withheld]
    if rest:
        said.append(f'méthodes {_numbers(rest)} à lire avec read_tiles(numbers)')
    shown['incomplete'] = (f'Code du chemin incomplet : {" ; ".join(said)}. La carte suit le graphe, pas '
                           'l’ordre d’exécution.')


def _numbers(numbers):
    return ', '.join(f'#{number}' for number in numbers)


def _limits(response):
    """Ce que les tuiles envoyées ne disent pas entièrement : code tronqué, en-têtes indisponibles, appels non suivis."""
    limits = {}
    truncated = [tile['number'] for tile in response['tiles'] if tile.get('truncated')]
    if truncated:
        limits['truncated_tiles'] = truncated
    headers = sorted({item['reference'] for item in response['not_sent']
                      if item.get('reason') == 'NOT_AVAILABLE' and item.get('what') != 'imports'})
    if headers:
        limits['unavailable_headers'] = headers
    unread = sorted({item['reference'] for item in response['not_sent'] if item.get('what') == 'imports'})
    if unread:
        limits['unavailable_imports'] = unread
    if response.get('not_followed'):
        limits['not_followed'] = response['not_followed']['count']
    return limits


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
    missing = {}
    if sources.OPERATION not in exchange.available():
        missing['NO_CONSENT'] = wanted
    else:
        _fill(exchange, response, numbered, wanted, _given(exchanged), max_bytes, missing)
    finished = _finish(response, numbered, missing, max_bytes)
    if size(_sized(finished)) > max_bytes:
        return error(OPERATION, exchange.snapshot, 'BUDGET_EXHAUSTED',
                     'La carte du chemin ne tient pas dans le budget de l’échange.')
    return finished


def _read(exchange, arguments, max_bytes, exchanged):
    numbers = arguments.get('numbers')
    if not isinstance(numbers, list) or not numbers or not all(type(value) is int for value in numbers):
        return error(READ, exchange.snapshot, _INVALID, 'numbers : une liste de numéros de la carte, ex. [2, 4].')
    paths = [item['response'] for item in exchanged
             if item.get('operation') == OPERATION and item['response'].get('outcome') == 'OK']
    if not paths:
        return error(READ, exchange.snapshot, _INVALID, 'Aucune carte reçue dans cet échange : demande d’abord get_path.')
    numbered = {entry['number']: entry['reference'] for entry in paths[-1]['map']}
    response = {'operation': READ, 'outcome': 'OK', 'snapshot': exchange.snapshot, 'tiles': [], 'not_sent': []}
    missing = {}
    unknown = sorted({value for value in numbers if value not in numbered})
    if unknown:
        missing['UNKNOWN_NUMBER'] = unknown
    wanted = [value for value in dict.fromkeys(numbers) if value in numbered]
    if sources.OPERATION not in exchange.available():
        missing.setdefault('NO_CONSENT', []).extend(wanted)
    elif wanted:
        _fill(exchange, response, numbered, wanted, _given(exchanged), max_bytes, missing)
    finished = _finish(response, {value: numbered[value] for value in wanted}, missing, max_bytes)
    if size(_sized(finished)) > max_bytes:
        return error(READ, exchange.snapshot, 'BUDGET_EXHAUSTED', 'Ces tuiles ne tiennent pas dans le budget.')
    return finished


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
