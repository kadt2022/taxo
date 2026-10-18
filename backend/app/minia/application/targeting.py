"""La cible B (MINIA_PATH_MODE=target) : le LLM désigne ce qu'il veut examiner, Taxo calcule le parcours, Minia livre
le code (vision du Capitaine Pi, 2026-10-16 ; simulateur B cible : 4/4 sur les questions de référence).

Le LLM ne reçoit que du code : le menu des points de départ que le graphe connaît, puis la carte du parcours et les
tuiles (classe annotée, méthode complète, champs utilisés, types nécessaires). Aucun fait de Taxo ne lui est transmis
(ni relations, ni règles d'URL) ; Taxo les garde pour calculer le parcours.

Une seule action pour le LLM, sous trois formes : désigner une cible (`target`), lire des tuiles de la carte (`read`),
ou dire qu'aucun code n'est utile (`none`) ; puis conclure (`answer`, texte libre). Le parcours et les tuiles sont
ceux de `paths` (budget, déduplication, consentement) : tout le code s'il tient, sinon ce qui tient et la liste à lire.
"""
import json
import re
from dataclasses import dataclass, field

from app.minia.application import paths
from app.minia.domain.errors import INVALID_ANSWER, MiniaError

TARGET, READ, NONE, ANSWER = 'target', 'read', 'none', 'answer'
MAX_TURNS = 6                 # appels au LLM par défaut (MINIA_TARGET_TURNS) : identification, choix, lecture, conclusion, garde
MIN_TURNS, MAX_ALLOWED_TURNS = 2, 20
MAX_CANDIDATES = 10
MENU_MAX = 30                 # au-delà, le menu est résumé et le LLM désigne sa cible par un nom
MAX_TARGETS = 4               # cibles désignées ensemble (« A, B »)
MAX_ANSWER = 20_000
ENTRY_ANNOTATIONS = frozenset({'Scheduled', 'KafkaListener', 'JmsListener', 'RabbitListener', 'EventListener',
                               'SqsListener'})
_ROUTE = re.compile(r'(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS) /')
ENDPOINT = 'endpoint:'
NO_CODE_YET = 'Aucun code reçu : désigne d’abord une cible (action "target") ou réponds "none".'
EXHAUSTED = 'L’échange avec Taxo est épuisé : conclus avec le code déjà reçu (action "answer").'
ALREADY = 'Déjà transmis plus haut dans ce dialogue : {}.'
PARTIAL = 'Réponse partielle, non vérifiée : établie sans avoir lu {} (dépendances directes du parcours).'
STALE = ('Réponse partielle, non vérifiée : rendue avant la lecture du code transmis ensuite ({}), qu’elle ne prend pas '
         'en compte.')
SEVERAL = ('Plusieurs parcours : l’action "read" porte sur le dernier ; pour lire une tuile d’un autre parcours, '
           'redésigne sa cible seule.')
_CANDIDATE = re.compile(r'[Cc](\d+)')

SYSTEM = (
    "Tu réponds à une question sur un projet Java à partir du code que Taxo te fournit (code exact, au commit analysé). "
    "Taxo calcule le parcours dans le code ; toi, tu choisis ce que tu veux lire et tu raisonnes.\n"
    "Réponds par un objet JSON, avec \"action\" :\n"
    "- \"target\" et \"target\" : ta cible — une entrée du menu, un nom de méthode ou de classe, ou des candidats "
    "proposés (C1, C2) ; plusieurs cibles séparées par des virgules ;\n"
    "- \"read\" et \"numbers\" : les numéros de la carte à lire, en une fois (seulement après avoir reçu une carte) ;\n"
    "- \"none\" : la question ne porte sur aucun code à lire (historique, couverture…) ;\n"
    "- \"answer\" et \"text\" : ta réponse, à partir du code reçu ; cite fichier:ligne, et sépare ce que le code "
    "établit, ce qui est une hypothèse et ce que le code reçu ne permet pas de savoir.\n"
    "Commence par \"target\" ou \"none\". Remplis toujours les quatre champs ; ceux qui ne servent pas restent vides "
    "(\"\" ou []).")

# Un schéma strict, comme celui de l'exploration : chaque champ requis (vide s'il ne sert pas), aucun autre champ. Claude
# exige `additionalProperties: false` et Mistral en mode strict des champs tous requis ; Gemini retire le premier.
SCHEMA = {'type': 'object', 'properties': {
    'action': {'type': 'string', 'enum': [TARGET, READ, NONE, ANSWER]},
    'target': {'type': 'string'}, 'numbers': {'type': 'array', 'items': {'type': 'integer'}},
    'text': {'type': 'string'}}, 'required': ['action', 'target', 'numbers', 'text'], 'additionalProperties': False}


def parse(raw):
    """Un tour du LLM : (action, valeur). MiniaError(INVALID_ANSWER) si la forme n'est pas celle demandée."""
    try:
        data = json.loads(raw)
    except (TypeError, ValueError) as exc:
        raise MiniaError(INVALID_ANSWER, "Minia n'a pas rendu de JSON lisible.") from exc
    action = data.get('action') if isinstance(data, dict) else None
    if action == TARGET and isinstance(data.get('target'), str) and data['target'].strip():
        return TARGET, data['target'].strip()[:500]
    if action == READ and isinstance(data.get('numbers'), list) and data['numbers'] \
            and all(type(value) is int for value in data['numbers']):
        return READ, list(dict.fromkeys(data['numbers']))
    if action == NONE:
        return NONE, None
    if action == ANSWER and isinstance(data.get('text'), str) and data['text'].strip():
        return ANSWER, data['text'].strip()[:MAX_ANSWER]
    raise MiniaError(INVALID_ANSWER, 'Minia n’a ni désigné de cible, ni demandé de tuiles, ni conclu.')


# --- Le menu des points de départ (uniquement ce que le graphe a observé) -------------------------------------------

def _assertions(exchange, **query):
    return [fact for fact in exchange.query(kind='ASSERTION', **query) if fact.get('validity', 'VALID') == 'VALID']


def _methods_of(exchange, owner):
    return sorted({fact['object'] for fact in _assertions(exchange, subject=owner, relation='CONTAINS')
                   if '#' in fact['object'] and '(' in fact['object'] and '#<init>' not in fact['object']
                   and '/' not in fact['object']})


def entries(exchange):
    """Les points de départ connus : endpoints (`HANDLED_BY`), méthodes annotées d'entrée, `main(String[])`."""
    endpoints = sorted({fact['subject'] for fact in _assertions(exchange, relation='HANDLED_BY')})
    annotated = sorted({fact['subject'] for fact in _assertions(exchange, relation='ANNOTATED_WITH')
                        if '#' in fact['subject']
                        and fact.get('object', '').rsplit('.', 1)[-1].removeprefix('annotation:') in ENTRY_ANNOTATIONS})
    mains = sorted({fact['object'] for fact in _assertions(exchange, relation='CONTAINS')
                    if fact['object'].endswith('#main(String[])')})
    return endpoints, annotated, mains


def menu(exchange):
    endpoints, annotated, mains = entries(exchange)
    found = [*endpoints, *annotated, *mains]
    if not found:
        text = 'Taxo ne connaît aucun point d’entrée dans ce projet : désigne ta cible par un nom de méthode ou de classe.'
    elif len(found) <= MENU_MAX:
        text = 'Points de départ connus de Taxo :\n' + '\n'.join(
            f'- {entry}' + (' (méthode annotée d’entrée)' if entry in annotated else ' (main)' if entry in mains else '')
            for entry in found)
    else:
        text = (f'{len(found)} points de départ connus (endpoints : {len(endpoints)}, méthodes annotées d’entrée : '
                f'{len(annotated)}, main : {len(mains)}) : désigne ta cible par un nom (méthode, classe ou chemin d’URL).')
    return text + '\nTu peux aussi désigner n’importe quelle méthode ou classe du projet par son nom.', set(endpoints)


# --- La résolution d'une cible -----------------------------------------------------------------------------------------

def _search(exchange, name, cache):
    """Les références dont le nom est `name` (index des noms de l'analyse), et la réponse de Taxo pour la trajectoire ; une
    recherche déjà faite dans ce dialogue n'est pas refaite (aucune étape)."""
    if name in cache:
        return cache[name], None
    arguments = {'analysis': exchange.snapshot['analysis'], 'prefix': name[:200], 'match': 'NAME', 'limit': 50}
    response = exchange.call({'operation': 'find_references', 'arguments': arguments})
    found = [item['reference'] for item in response.get('items') or ()] if response['outcome'] == 'OK' else []
    cache[name] = found
    return found, ('find_references', arguments, response)


def _methods_named(exchange, name, cache):
    """Les méthodes que désigne un nom : la méthode elle-même, ou celles de la classe nommée."""
    found, step = _search(exchange, name, cache)
    methods = [reference for reference in found if '#' in reference and '(' in reference]
    for owner in (reference for reference in found if '#' not in reference):
        methods += [method for method in _methods_of(exchange, owner) if method not in methods]
    return methods, step


def _route(item):
    """La référence d'un endpoint écrit tel quel (`endpoint:GET /x`) ou par sa seule route (`GET /x`), sinon None."""
    if item.startswith(ENDPOINT):
        return item
    if _ROUTE.match(item):
        return f'{ENDPOINT}{item}'
    return None


def split(target):
    """Les cibles d'une demande, séparées par des virgules hors parenthèses : une signature Java
    (`PolicyEvaluator.evaluate(Subject,Resource)`) reste entière."""
    items, depth, current = [], 0, ''
    for char in target:
        depth += (char == '(') - (char == ')')
        if char == ',' and depth <= 0:
            items.append(current)
            current, depth = '', 0
        else:
            current += char
    items.append(current)
    return [item.strip().strip('`"«» ') for item in items if item.strip().strip('`"«» ')]


@dataclass
class Resolution:
    """Ce que Taxo trouve pour une demande : les départs servis tout de suite, les candidats des seuls noms ambigus, les
    noms trop larges (nom, nombre) et les noms inconnus, et les étapes Taxo faites pour le savoir."""
    starts:list=field(default_factory=list)
    candidates:list=field(default_factory=list)
    too_many:list=field(default_factory=list)
    unknown:list=field(default_factory=list)
    steps:list=field(default_factory=list)


def resolve(exchange, target, known_endpoints, pending, limit=MAX_TARGETS, cache=None):
    """Chaque cible de la demande, résolue à part : un départ unique est servi, plusieurs départs deviennent des candidats
    (sans y mêler ce qui est résolu), aucun est dit. Au plus `limit` cibles : ce que l'échange peut encore servir."""
    cache = {} if cache is None else cache
    found = Resolution()
    for item in split(target)[:min(MAX_TARGETS, limit)]:
        starts, ambiguous = _starts(exchange, item, known_endpoints, pending, cache, found.steps)
        if starts:
            found.starts += [start for start in starts if start not in found.starts]
        elif len(ambiguous) > MAX_CANDIDATES:
            found.too_many.append((item, len(ambiguous)))
        elif ambiguous:
            found.candidates += [candidate for candidate in ambiguous if candidate not in found.candidates]
        else:
            found.unknown.append(item)
    if len(found.candidates) > MAX_CANDIDATES:
        # Le plafond vaut pour la liste combinée : plusieurs noms ambigus ne font pas un menu démesuré.
        found.too_many.append(('cette demande', len(found.candidates)))
        found.candidates = []
    return found


def _starts(exchange, item, known_endpoints, pending, cache, steps):
    """Une cible : ([départ], [candidats]) ; ([], []) si rien ne lui répond."""
    chosen = _CANDIDATE.fullmatch(item)
    if chosen:
        index = int(chosen.group(1))
        return ([pending[index - 1]], []) if 1 <= index <= len(pending) else ([], [])
    route = _route(item)
    if route:
        return ([route], []) if route in known_endpoints else ([], [])
    methods, step = _methods_named(exchange, item.removeprefix('symbol:java:'), cache)
    if step:
        steps.append(step)
    return (methods, []) if len(methods) == 1 else ([], methods)


def short(reference):
    key = reference.removeprefix('symbol:java:').removeprefix(ENDPOINT)
    owner, _, member = key.partition('#')
    if member:
        return f'{owner.rsplit(".", 1)[-1]}.{member}'
    if reference.startswith(ENDPOINT):
        return owner
    return owner.rsplit('.', 1)[-1]


# --- Ce que le LLM reçoit : du code, et la carte pour choisir ---------------------------------------------------------

def _tile_text(tile):
    out = []
    if 'class' in tile:
        head = tile['class']
        out.append(f'--- classe {short(head["reference"])} ({head["path"]}:{head["line_start"]}) ---\n{head["text"]}')
    out.append(f'--- #{tile["number"]} {short(tile["reference"])} ({tile["path"]}:{tile["line_start"]}-'
               f'{tile["line_end"]}){" [tronqué]" if tile.get("truncated") else ""} ---')
    if tile.get('fields'):
        out.append('champs utilisés :\n' + '\n'.join(tile['fields']))
    out.append(tile['code'])
    for head in tile.get('types') or ():
        out.append(f'--- type {short(head["reference"])} ({head["path"]}:{head["line_start"]}) ---\n{head["text"]}')
    return '\n'.join(out)


def _missing(response):
    """Ce qui n'est pas parti, dit au LLM sans les faits de Taxo : tuiles à lire, code non autorisé, en-têtes."""
    said = []
    for item in response.get('not_sent') or ():
        if item.get('what') == 'tiles' and item.get('reason') == 'NO_CONSENT':
            said.append('Code non autorisé pour cette demande : seule la carte est transmise.')
        elif item.get('what') == 'tiles' and item.get('reason') == 'UNKNOWN_NUMBER':
            said.append('Numéros inconnus : ' + ', '.join(f'#{n}' for n in item['numbers']) + '.')
        elif item.get('what') == 'tiles' and item.get('reason') not in ('BUDGET',):
            said.append('Code illisible : ' + ', '.join(f'#{n}' for n in item['numbers']) + '.')
        elif item.get('what') in ('class_header', 'type_header'):
            said.append(f'En-tête indisponible : {short(item["reference"])}.')
    if response.get('to_read'):
        said.append('Code du parcours non encore transmis : ' + ', '.join(f'#{n}' for n in response['to_read'])
                    + ' (action "read").')
    return said


def render_path(response):
    """La carte d'un parcours (`get_path`) et les tuiles qui tiennent, en texte."""
    if response.get('outcome') != 'OK':
        return f'Taxo ne peut pas calculer ce parcours : {response["error"]["message"]}'
    lines = [f'Parcours depuis {short(response["reference"])} ({len(response["map"])} méthodes ; la carte suit le '
             'graphe, pas l’ordre d’exécution)']
    for entry in response['map']:
        line = f'#{entry["number"]} {entry["name"]}'
        if entry.get('role') == 'filter_chain':
            line += ' [chaîne de filtres de la route]'
        callees = [f'#{callee}' if isinstance(callee, int) else short(callee) + ' (hors parcours)'
                   for callee in entry.get('calls') or ()]
        if callees:
            line += '  → appelle ' + ', '.join(callees)
        if entry.get('frontier'):
            line += '  [contient des appels que Taxo ne suit pas]'
        lines.append(line)
    if response.get('not_followed'):
        lines.append(f'{response["not_followed"]["count"]} appel(s) au-delà de la profondeur du parcours, non suivis.')
    return '\n\n'.join(part for part in ('\n'.join(lines), *map(_tile_text, response['tiles']),
                                         '\n'.join(_missing(response))) if part)


def render_read(response):
    """Des tuiles lues (`read_tiles`), en texte."""
    if response.get('outcome') != 'OK':
        return f'Taxo ne peut pas lire ces tuiles : {response["error"]["message"]}'
    return '\n\n'.join(part for part in (*map(_tile_text, response['tiles']), '\n'.join(_missing(response))) if part)


def render_candidates(candidates):
    return ('Plusieurs candidats ; désigne-en un ou plusieurs (« C1 » ou « C1, C2 ») :\n'
            + '\n'.join(f'C{index} {short(reference)}' for index, reference in enumerate(candidates, 1)))


def message(question, menu_text, turns, calls_left):
    """Le message du tour (JSON, que la confidentialité protège champ par champ) : la question, le menu, puis chaque
    demande du LLM et ce que Taxo lui a rendu, en texte."""
    payload = {'question': question, 'menu': menu_text,
               'turns': [{'asked': asked, 'taxo': answered} for asked, answered in turns], 'calls_left': calls_left}
    if calls_left <= 1:
        payload['instruction'] = 'Conclus maintenant (action "answer").'
    return json.dumps(payload, ensure_ascii=False, separators=(',', ':'))


# --- La garde : les dépendances formelles du parcours, jamais la pertinence ------------------------------------------

def unread(exchanged):
    """Les dépendances formelles non lues de chaque carte servie : la chaîne de filtres d'une route et les méthodes
    appelées directement par l'entrée. Une lecture (`read`) porte sur la dernière carte reçue ; une tuile sans code
    lisible n'est jamais rappelée, seule une tuile retenue par le budget l'est. Les numéros d'une carte précédente
    portent le nom de son départ (« ItemService.add(Long) #2 »)."""
    maps = []
    for item in exchanged:
        response = item['response']
        if item['operation'] == paths.OPERATION and response.get('outcome') == 'OK':
            maps.append((response, set(), set()))
        elif item['operation'] != paths.READ or not maps:
            continue
        _, read, unreadable = maps[-1]
        read |= {tile['number'] for tile in response.get('tiles') or ()}
        unreadable |= _unreadable(response)
    missed = []
    for position, (path, read, unreadable) in enumerate(maps):
        if not read:
            continue  # aucun code lu (consentement absent) : rien à rappeler
        prefix = '' if position == len(maps) - 1 else f'{short(path["reference"])} '
        missed += [f'{prefix}#{number}' for number in sorted(_formal(path) - read - unreadable)]
    return missed


def _formal(path):
    entry = path['map'][0]
    formal = {number for number in entry.get('calls') or () if isinstance(number, int)}
    if path['reference'].startswith(ENDPOINT):
        formal |= {item['number'] for item in path['map'] if item.get('role') == 'filter_chain'}
    return formal


def _unreadable(response):
    """Les numéros dont le code n'est pas lisible (accesseur implicite de record, source illisible) : tout ce qui n'est
    pas parti pour une autre raison que le budget."""
    return {number for missing in response.get('not_sent') or ()
            if missing.get('what') == 'tiles' and missing.get('reason') != 'BUDGET'
            for number in missing.get('numbers') or ()}


def recall(missed):
    return ('Non lus : ' + ', '.join(missed) + ' (dépendances directes du parcours). Lis-les (action "read" ; pour un '
            'parcours précédent, redésigne sa cible seule) ou redonne ta conclusion telle quelle.')
