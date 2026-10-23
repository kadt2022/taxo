"""Couverture des symboles des tuiles (récit TAXO-RECIT-CONTRAT-SUFFISANCE-STRUCTURELLE-DES-TUILES, lot S0).

Pour des méthodes d'un dépôt Git analysé, mesure ce que la tuile actuelle de Minia (`paths._tile`) donne au lecteur :
chaque nom utilisé dans la méthode est-il identifié dans la tuile, connu de Taxo sans que la tuile le porte, ou non résolu ?

Les « symboles pertinents » sont établis par une analyse lexicale **indépendante** de l'évaluateur : un nom qui désigne une
déclaration (variable, paramètre, champ, méthode, type), sans les mots-clés ni les littéraux. L'analyse est approchée : elle
ne comprend pas Java, et ses limites sont dites dans le rapport.

Usage (depuis `backend`) :
    python scripts/tile_symbol_coverage.py <dépôt> [--commit SHA] [--limit 25] [--classes A,B] [--database URL]

Sans `--database`, une base SQLite temporaire. Le résultat est du Markdown sur la sortie standard. Lecture seule sur le dépôt.
"""
import argparse
import re
import sys
import tempfile
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.protocol.domain.source import import_target  # noqa: E402

KEYWORDS = frozenset(
    'abstract assert boolean break byte case catch char class const continue default do double else enum extends final finally '
    'float for goto if implements import instanceof int interface long native new package private protected public return short '
    'static strictfp super switch synchronized this throw throws transient try void volatile while true false null var record '
    'sealed permits yield'.split())

# Les rôles d'un nom dans le texte d'une méthode.
LOCAL, FIELD, TYPE, CALL, MEMBER_CALL, MEMBER = 'local', 'field', 'type', 'call', 'member_call', 'member'
# L'état d'un symbole dans la tuile : porté ; identifié par un import (nom complet connu, type non résolu) ; identifié par la règle
# du langage (`java.lang`) ; connu de Taxo sans être porté ; non résolu.
IN_TILE, IMPORTED, IMPLICIT = 'in_tile', 'imported', 'implicit'
KNOWN_NOT_CARRIED, UNRESOLVED = 'known_not_carried', 'unresolved'

_TOKEN = re.compile(r'(?<![\w$])[A-Za-z_$][\w$]*')
# Chaînes et commentaires en une seule passe : un `//` dans une chaîne (`"http://host"`) n'est pas un commentaire, et un guillemet dans
# un commentaire n'ouvre pas une chaîne.
_LITERALS = re.compile(r'"""(?:.|\n)*?"""|"(?:\\.|[^"\\\n])*"|\'(?:\\.|[^\'\\\n])*\'|//[^\n]*|/\*.*?\*/', re.DOTALL)
_DECLARATION = re.compile(r'(?:^|[;{}(])\s*(?:final\s+)?([A-Za-z_][\w.]*(?:<[^;(){}]*>)?(?:\[\])*)\s+([a-z_]\w*)\s*(?==|;|:|,|\))',
                          re.MULTILINE)


def clean(code):
    """Le code sans commentaires ni chaînes (leur contenu n'est pas un symbole), les sauts de ligne conservés."""
    return _LITERALS.sub(lambda match: re.sub(r'[^\n]', ' ', match.group(0)), code)


def written_name(method):
    """Le nom que la déclaration écrit : celui de la méthode, ou, pour un constructeur (`<init>`), le nom simple de sa classe."""
    name = method.split('#', 1)[1].split('(')[0]
    return method.split('#', 1)[0].rsplit('.', 1)[-1].rsplit(':', 1)[-1] if name == '<init>' else name


def declared_names(code):
    """Les noms que la méthode déclare elle-même : paramètres, variables locales, paramètres de lambda, de catch, de motif."""
    text = clean(code)
    names = set()
    head = text[:text.find('{')] if '{' in text else text
    parameters = head[head.find('(') + 1:head.rfind(')')] if '(' in head else ''
    depth, piece = 0, ''
    for char in parameters + ',':
        depth += char in '<(['
        depth -= char in '>)]'
        if char == ',' and depth <= 0:
            found = _TOKEN.findall(piece)
            if found:
                names.add(found[-1])
            piece = ''
        else:
            piece += char
    for match in _DECLARATION.finditer(text[len(head):]):
        if match.group(1) not in KEYWORDS - {'var', 'int', 'long', 'boolean', 'double', 'float', 'char', 'byte', 'short'}:
            names.add(match.group(2))
    names.update(re.findall(r'\b([a-z_]\w*)\s*->', text))
    for group in re.findall(r'\(([^()]*)\)\s*->', text):
        names.update(name for name in _TOKEN.findall(group) if name not in KEYWORDS and name[0].islower())
    names.update(re.findall(r'catch\s*\(\s*[\w.|\s]+?\s+(\w+)\s*\)', text))
    names.update(re.findall(r'instanceof\s+[\w.<>]+\s+(\w+)', text))
    return names


def _used_as_type(before, after):
    """Un nom tout en majuscules écrit comme un type : suivi de `::`, d'un nom (`UUID id`), de `<` ou de `[`, ou argument de type
    (`Set<UUID>`). Une constante n'est jamais suivie d'un nom. Suivi d'un point (`UUID.fromString` ou `TOKEN.equals`), le texte
    ne tranche pas : un import le fait (voir `resolve`)."""
    return (after.startswith(('::', '<', '[')) or bool(re.match(r'[A-Za-z_$]', after))
            or (after.startswith('>') and before.endswith(('<', ','))))


def symbols(code, own_name=None, fixed=False):
    """Les symboles pertinents de la méthode, par (nom, rôle) : ce qu'elle utilise et doit être identifié par le lecteur.

    `fixed` : corrige un biais de l'analyse du lot S0 : un nom tout en majuscules écrit comme un type (`UUID.fromString`,
    `UUID id`, `Set<UUID>`) est un type, pas une constante."""
    text = clean(code)
    found, seen_own = {}, own_name is None
    for match in _TOKEN.finditer(text):
        name = match.group(0)
        before = text[:match.start()].rstrip()
        after = text[match.end():].lstrip()
        if name in KEYWORDS:
            continue
        if not seen_own and name == own_name and after.startswith('('):
            seen_own = True
            continue
        if before.endswith('@'):
            role = TYPE
        elif before.endswith('.'):
            role = MEMBER_CALL if after.startswith('(') else MEMBER
        elif before.endswith('new') and re.search(r'(?<![\w$])new$', before):
            role = TYPE
        elif after.startswith('('):
            role = CALL
        elif re.fullmatch(r'[A-Z][A-Z0-9_]+', name):
            role = TYPE if fixed and _used_as_type(before, after) else MEMBER
        elif name[0].isupper():
            if len(name) == 1:
                continue
            role = TYPE
        else:
            role = FIELD
        found.setdefault((name, role), match.start())
    return found


# Les types du paquet `java.lang`, visibles sans import.
JAVA_LANG = frozenset(
    'Object String Integer Long Short Byte Double Float Boolean Character Number Math StringBuilder StringBuffer System Thread Runnable '
    'Iterable Comparable Class Enum Record Void Throwable Exception RuntimeException Error AutoCloseable CharSequence Override '
    'Deprecated FunctionalInterface SuppressWarnings SafeVarargs IllegalArgumentException IllegalStateException '
    'NullPointerException UnsupportedOperationException IndexOutOfBoundsException ArithmeticException ClassCastException '
    'InterruptedException CloneNotSupportedException AssertionError'.split())


def import_kind(name, source):
    """Ce que le texte du fichier dit d'un nom de type : `import` (un import simple le désigne), `java.lang` (visible sans
    import), `wildcard` (un import avec joker ne dit pas lequel), ou `none` (même paquet, inconnu ou externe sans import)."""
    if re.search(rf'^import\s+(?:static\s+)?[\w.]+\.{re.escape(name)}\s*;', source, re.MULTILINE):
        return 'import'
    if name in JAVA_LANG:
        return 'java.lang'
    if re.search(r'^import\s+(?:static\s+)?[\w.]+\.\*\s*;', source, re.MULTILINE):
        return 'wildcard'
    return 'none'


def field_names(fields):
    """Les noms des champs dont la tuile porte la déclaration."""
    names = set()
    for text in fields:
        match = re.search(r'([A-Za-z_$][\w$]*)\s*(?:=|;|$)', clean(text).strip().split('\n')[0])
        if match:
            names.add(match.group(1))
    return names


def type_names(tile):
    """Les noms de types dont la tuile porte l'en-tête : la classe et les types joints."""
    names = set()
    headers = [tile['class']['text']] if tile.get('class') else []
    headers += [item.get('text', '') for item in tile.get('types', ())]
    for text in headers:
        match = re.search(r'\b(?:class|interface|enum|record)\s+([A-Za-z_$][\w$]*)', clean(text))
        if match:
            names.add(match.group(1))
    return names


@dataclass(frozen=True)
class Resolution:
    name: str
    role: str
    state: str
    how: str


# Les annotations Lombok qui déclarent un champ `log` : le champ n'est écrit nulle part, l'annotation de la classe le déclare.
LOMBOK_LOGGER = re.compile(r'@(Slf4j|Log4j2|Log4j|Log|CommonsLog|JBossLog|Flogger|XSlf4j|CustomLog)\b')


def imported_names(tile):
    """Les noms simples que les imports de la tuile désignent (hors jokers, qui ne désignent qu'un paquet), avec leur import."""
    named, wildcards = {}, []
    for entry in tile.get('imports') or ():
        target = import_target(entry['text'])
        if target is None:
            continue
        if target[1]:
            wildcards.append(entry['text'])
        else:
            named[target[0].rsplit('.', 1)[-1]] = entry['text']
    return named, wildcards


def resolve(found, code, tile, known, fixed=False):
    """L'état de chaque symbole : porté par la tuile, identifié par un import, connu de Taxo sans que la tuile le porte, ou non
    résolu.

    `known` : `types` (noms simples des types du projet), `calls` (noms des méthodes que Taxo relie par CALLS) et `members`
    (noms des méthodes déclarées par la classe). `fixed` : les corrections de l'outil du lot S0 (un champ `log` déclaré par une
    annotation Lombok de la classe, les types de `java.lang` identifiés par la règle du langage) ; sans elles, les règles du lot S0.
    Un import identifie un nom complet, il ne résout pas le type : un joker ne désigne jamais un type."""
    own = declared_names(code)
    fields, types = field_names(tile.get('fields', ())), type_names(tile)
    named, wildcards = imported_names(tile)
    header = (tile.get('class') or {}).get('text', '')
    lombok = LOMBOK_LOGGER.search(clean(header))
    out = []
    for (name, role), _ in found.items():
        if role in (FIELD, LOCAL) and name in own:
            out.append(Resolution(name, LOCAL, IN_TILE, 'déclaré dans la méthode'))
        elif role == FIELD and name in fields:
            out.append(Resolution(name, role, IN_TILE, 'déclaration du champ dans la tuile'))
        elif fixed and role == FIELD and name == 'log' and lombok:
            out.append(Resolution(name, role, IN_TILE, f'champ généré par @{lombok.group(1)}, dans l’en-tête de la tuile'))
        elif role == TYPE and name in types:
            out.append(Resolution(name, role, IN_TILE, 'en-tête du type dans la tuile'))
        elif fixed and role == MEMBER and name in named and name.isupper():
            out.append(Resolution(name, TYPE, IMPORTED, named[name]))
        elif role == TYPE and name in named:
            out.append(Resolution(name, role, IMPORTED, named[name]))
        elif role == TYPE and name in known['types']:
            out.append(Resolution(name, role, KNOWN_NOT_CARRIED, 'type du projet, en-tête absent de la tuile'))
        elif fixed and role == TYPE and name in JAVA_LANG:
            out.append(Resolution(name, role, IMPLICIT, 'type de java.lang, visible sans import'))
        elif role == TYPE and wildcards:
            out.append(Resolution(name, role, UNRESOLVED, 'joker présent, paquets candidats : ' + ', '.join(wildcards)))
        elif role in (CALL, MEMBER_CALL) and name in known['calls']:
            out.append(Resolution(name, role, KNOWN_NOT_CARRIED, 'appel relié par Taxo, signature absente de la tuile'))
        elif role == CALL and name in known['members']:
            out.append(Resolution(name, role, KNOWN_NOT_CARRIED, 'méthode de la classe, signature absente de la tuile'))
        else:
            out.append(Resolution(name, role, UNRESOLVED, 'aucune déclaration dans la tuile ni dans les faits'))
    return out


def coverage(resolutions):
    """Les deux couvertures d'une méthode : stricte (portée par la tuile) et avec les liens connus de Taxo."""
    total = len(resolutions)
    carried = sum(item.state == IN_TILE for item in resolutions)
    linked = carried + sum(item.state in (KNOWN_NOT_CARRIED, IMPORTED, IMPLICIT) for item in resolutions)
    return (carried / total if total else 1.0), (linked / total if total else 1.0)


def metrics(resolutions):
    """Les quatre mesures d'un ensemble de symboles, du plus strict au plus large : portés par la tuile ; identifiés par la
    tuile (portés ou importés) ; identifiés avec la règle du langage (`java.lang`) ; avec les liens connus de Taxo."""
    total = len(resolutions)
    count = Counter(item.state for item in resolutions)
    carried, imported, implicit, known = count[IN_TILE], count[IMPORTED], count[IMPLICIT], count[KNOWN_NOT_CARRIED]
    share = (lambda number: number / total if total else 1.0)
    return {'total': total, 'carried': carried, 'imported': imported, 'implicit': implicit, 'known': known,
            'unresolved': count[UNRESOLVED], 'strict': share(carried), 'identified': share(carried + imported),
            'language': share(carried + imported + implicit), 'links': share(carried + imported + implicit + known)}


def pick(methods, limit, wanted):
    """Un échantillon déterministe : les méthodes demandées d'abord, puis des méthodes régulièrement espacées."""
    chosen = [method for method in methods if any(method.endswith(f'#{name}') or f'#{name}(' in method for name in wanted)]
    rest = [method for method in methods if method not in chosen]
    room = max(limit - len(chosen), 0)
    step = max(len(rest) // room, 1) if room else 1
    return (chosen + rest[::step][:room])[:limit]


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('repository', type=Path)
    parser.add_argument('--commit')
    parser.add_argument('--limit', type=int, default=25)
    parser.add_argument('--classes', default='')
    parser.add_argument('--wanted', default='authorize,assertActorInSpaceOrg,doFilterInternal')
    parser.add_argument('--database')
    options = parser.parse_args()
    repository = options.repository.resolve()
    if options.database:
        run(options.database, repository, options)
        return
    with tempfile.TemporaryDirectory(prefix='taxo-coverage-') as folder:
        run(f'sqlite:///{folder}/taxo.db', repository, options)


def run(database, repository, options):
    from fastapi.testclient import TestClient

    from app.main import create_app
    from app.minia.application import paths
    from app.platform.database.base import Base

    app = create_app(database, [repository], minia={}, source_reading='symbol')
    Base.metadata.create_all(app.state.engine)
    try:
        with TestClient(app) as client:
            created = client.post('/api/projects', json={'name': repository.name, 'path': str(repository)})
            created.raise_for_status()
            project = created.json()['id']
            start = time.perf_counter()
            scanned = client.post(f'/api/projects/{project}/scans', params={'commit': options.commit} if options.commit else {})
            scanned.raise_for_status()
            seconds = time.perf_counter() - start
            analysis = scanned.json()
            exchange = app.state.taxo_query.open(project, source_consent=True, max_bytes=200_000, analysis_id=analysis['id'])
            report(exchange, paths, repository, analysis, seconds, options)
    finally:
        app.state.engine.dispose()


def methods_of(exchange, classes):
    found = sorted({fact['object'] for fact in exchange.query(relation='CONTAINS', kind='ASSERTION')
                    if fact['object'].startswith('symbol:') and '#' in fact['object'] and '(' in fact['object']
                    and '/' not in fact['object'].split('#', 1)[1]})
    if classes:
        found = [method for method in found if any(f'.{name}#' in method for name in classes)]
    return found


def tile_size(tile, with_imports):
    """Les octets d'une tuile pour le modèle : code, champs, en-tête de classe, et, si demandé, ses imports."""
    size = len(tile['code'].encode()) + sum(len(text.encode()) for text in tile['fields'])
    size += len((tile.get('class') or {}).get('text', '').encode())
    if with_imports:
        size += sum(len(entry['text'].encode()) + 1 for entry in tile.get('imports') or ())
    return size


def build(exchange, paths, methods):
    """Les tuiles de chaque méthode, chacune construite seule, avec ce que Taxo connaît de ses appels, de ses types et de sa classe."""
    context = {'headers': {}, 'types': paths._project_types(exchange)}
    known_types, built, refused = set(context['types']), [], Counter()
    for method in methods:
        tile, reason, _, _ = paths._tile(exchange, 1, method, context, set())
        if tile is None:
            refused[reason] += 1
            continue
        owner = method.split('#', 1)[0]
        calls = {fact['object'].split('#')[-1].split('(')[0] for fact in exchange.query(subject=method, relation='CALLS', kind='ASSERTION')}
        members = {fact['object'].split('#', 1)[1].split('(')[0] for fact in exchange.query(subject=owner, relation='CONTAINS', kind='ASSERTION')
                   if '#' in fact['object'] and '(' in fact['object']}
        built.append((method, tile, {'types': known_types, 'calls': calls, 'members': members}))
    return built, refused


def resolutions_of(tile, known, own_name, with_imports, fixed):
    """Les symboles de la tuile, résolus avec ou sans ses imports, avec les règles du lot S0 ou corrigées."""
    seen = tile if with_imports else {key: value for key, value in tile.items() if key != 'imports'}
    return resolve(symbols(tile['code'], own_name, fixed), tile['code'], seen, known, fixed)


# Les méthodes que Minia a lues dans l'essai 3 (TAKIBO, 2026-10-17) : cinq de deux classes de sécurité, six de `PolicyEvaluator`.
ESSAI3 = ('SecurityConfig#securityFilterChain(', 'PolicyBasedAuthorizationManager#authorize(',
          'PolicyBasedAuthorizationManager#evaluateAdaptiveDecision(', 'PolicyBasedAuthorizationManager#extractPermissions(',
          'PolicyBasedAuthorizationManager#extractRoles(', 'PolicyEvaluator#evaluate(', 'PolicyEvaluator#evaluateTenantIsolation(',
          'PolicyEvaluator#evaluateResourcePolicies(', 'PolicyEvaluator#isTenantAdmin(', 'PolicyEvaluator#denyTmsSpaceSurface(',
          'PolicyEvaluator#denyOrgDashboardSurface(')

CONFIGURATIONS = (('Lot S0 : tuile sans imports, règles du lot S0', False, False),
                  ('Tuile avec imports, règles du lot S0', True, False),
                  ('Tuile sans imports, outil corrigé (`UUID`, Lombok, `java.lang`)', False, True),
                  ('Tuile avec imports, outil corrigé', True, True))


def sequential_import_bytes(exchange, paths, methods):
    """Les octets d'imports envoyés par les tuiles d'un même échange, avec la déduplication, et sans elle."""
    context = {'headers': {}, 'types': paths._project_types(exchange)}
    given, deduplicated, repeated = set(), 0, 0
    for method in methods:
        tile, _, adds, _ = paths._tile(exchange, 1, method, context, given)
        if tile is None:
            continue
        deduplicated += sum(len(entry['text'].encode()) + 1 for entry in tile.get('imports') or ())
        given |= adds
    for method in methods:
        tile, _, _, _ = paths._tile(exchange, 1, method, context, set())
        repeated += sum(len(entry['text'].encode()) + 1 for entry in (tile or {}).get('imports') or ())
    return deduplicated, repeated


def report(exchange, paths, repository, analysis, seconds, options):
    classes = [name for name in options.classes.split(',') if name]
    wanted = [name for name in options.wanted.split(',') if name]
    methods = pick(methods_of(exchange, classes), options.limit, wanted)
    built, refused = build(exchange, paths, methods)
    facts = sum(item['fact_count'] for item in analysis['evaluations'])
    print(f'# Couverture des symboles des tuiles — {repository.name}\n')
    print(f'Analyse complète : {seconds:.1f} s, {facts} faits, `{analysis["id"]}`. {len(methods)} méthodes retenues, '
          f'{len(built)} tuiles construites, refusées : {dict(refused) or "aucune"}.\n')
    results = {}
    for label, with_imports, fixed in CONFIGURATIONS:
        every = [item for method, tile, known in built
                 for item in resolutions_of(tile, known, written_name(method), with_imports, fixed)]
        results[label] = (metrics(every), every)
    print('| Configuration | Symboles | Portés par la tuile | Identifiés par la tuile | Avec la règle du langage | Avec les liens connus | Non résolus |')
    print('| --- | --- | --- | --- | --- | --- | --- |')
    for label, (measured, _) in results.items():
        print(f'| {label} | {measured["total"]} | {measured["strict"]:.1%} ({measured["carried"]}) '
              f'| {measured["identified"]:.1%} ({measured["carried"] + measured["imported"]}) '
              f'| {measured["language"]:.1%} | {measured["links"]:.1%} | {measured["unresolved"]} |')
    print('\nLecture : « portés » = la tuile porte la déclaration ; « identifiés par la tuile » = portés, ou nom complet donné par un import '
          '(le type n’est pas résolu pour autant) ; « règle du langage » ajoute les types de `java.lang`, visibles sans import (une règle de '
          'l’outil, pas un contenu de la tuile) ; « liens connus » ajoute ce que Taxo relie sans que la tuile le porte.\n')
    after = results[CONFIGURATIONS[1][0]][1]
    wildcard = [item for item in after if item.state == UNRESOLVED and item.role == TYPE and item.how.startswith('joker')]
    types = [item for item in after if item.role == TYPE]
    print(f'Types : {len(types)} ; identifiés par un import : {sum(item.state == IMPORTED for item in types)} ; '
          f'non résolus alors qu’un joker est présent (paquets candidats, rien d’inventé) : {len(wildcard)}.\n')
    deduplicated, repeated = sequential_import_bytes(exchange, paths, [method for method, _, _ in built])
    imports_bytes = sum(tile_size(tile, True) - tile_size(tile, False) for _, tile, _ in built)
    base_bytes = sum(tile_size(tile, False) for _, tile, _ in built)
    print(f'Coût : les imports ajoutent {imports_bytes} octets aux {base_bytes} octets de ces tuiles ({imports_bytes / base_bytes:.1%}) ; '
          f'envoyées dans un même échange, les mêmes tuiles portent {deduplicated} octets d’imports au lieu de {repeated} '
          f'({1 - deduplicated / repeated:.0%} de moins grâce à la déduplication).\n' if base_bytes and repeated else '\n')
    scenario = [method for method in methods_of(exchange, []) if any(f'.{pattern}' in method for pattern in ESSAI3)]
    if scenario:
        kept, repeated_all = sequential_import_bytes(exchange, paths, scenario)
        print(f'Scénario de l’essai 3 ({len(scenario)} méthodes lues dans un même échange) : {kept} octets d’imports avec la déduplication, '
              f'{repeated_all} sans ({1 - kept / repeated_all:.0%} de moins) ; un fichier dont plusieurs méthodes sont lues ne redonne '
              'jamais le même import.\n' if repeated_all else '\n')
    print('| Méthode | Symboles | Portés | Identifiés avant → après (outil corrigé) | Non résolus après |')
    print('| --- | --- | --- | --- | --- |')
    for method, tile, known in built:
        name = written_name(method)
        before = metrics(resolutions_of(tile, known, name, False, True))
        now = metrics(resolutions_of(tile, known, name, True, True))
        print(f'| `{paths._short(method)}` | {now["total"]} | {now["strict"]:.0%} | {before["identified"]:.0%} → {now["identified"]:.0%} '
              f'| {now["unresolved"]} |')
    remaining = Counter((item.name, item.role) for item in results[CONFIGURATIONS[3][0]][1] if item.state == UNRESOLVED)
    print('\n| Reste non résolu (tuile avec imports, outil corrigé) | Rôle | Méthodes |')
    print('| --- | --- | --- |')
    for (name, role), count in remaining.most_common(20):
        print(f'| `{name}` | {role} | {count} |')


if __name__ == '__main__':
    main()
