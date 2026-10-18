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

KEYWORDS = frozenset(
    'abstract assert boolean break byte case catch char class const continue default do double else enum extends final finally '
    'float for goto if implements import instanceof int interface long native new package private protected public return short '
    'static strictfp super switch synchronized this throw throws transient try void volatile while true false null var record '
    'sealed permits yield'.split())

# Les rôles d'un nom dans le texte d'une méthode.
LOCAL, FIELD, TYPE, CALL, MEMBER_CALL, MEMBER = 'local', 'field', 'type', 'call', 'member_call', 'member'
# L'état d'un symbole dans la tuile.
IN_TILE, KNOWN_NOT_CARRIED, UNRESOLVED = 'in_tile', 'known_not_carried', 'unresolved'

_TOKEN = re.compile(r'(?<![\w$])[A-Za-z_$][\w$]*')
_COMMENTS = re.compile(r'//[^\n]*|/\*.*?\*/', re.DOTALL)
_STRINGS = re.compile(r'"""(?:.|\n)*?"""|"(?:\\.|[^"\\\n])*"|\'(?:\\.|[^\'\\\n])*\'')


def clean(code):
    """Le code sans commentaires ni chaînes (leur contenu n'est pas un symbole), les sauts de ligne conservés."""
    def blank(match):
        return re.sub(r'[^\n]', ' ', match.group(0))
    return _STRINGS.sub(blank, _COMMENTS.sub(blank, code))


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
    for match in re.finditer(r'\b(?:final\s+)?([A-Za-z_][\w.<>\[\]?, ]*?)\s+([a-z_]\w*)\s*(?==|;|:|,|\))', text[len(head):]):
        if match.group(1).split()[0] not in KEYWORDS - {'var', 'int', 'long', 'boolean', 'double', 'float', 'char', 'byte', 'short'}:
            names.add(match.group(2))
    names.update(re.findall(r'\b([a-z_]\w*)\s*->', text))
    for group in re.findall(r'\(([^()]*)\)\s*->', text):
        names.update(name for name in _TOKEN.findall(group) if name not in KEYWORDS and name[0].islower())
    names.update(re.findall(r'catch\s*\(\s*[\w.|\s]+?\s+(\w+)\s*\)', text))
    names.update(re.findall(r'instanceof\s+[\w.<>]+\s+(\w+)', text))
    return names


def symbols(code, own_name=None):
    """Les symboles pertinents de la méthode, par (nom, rôle) : ce qu'elle utilise et doit être identifié par le lecteur."""
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
            role = MEMBER
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


def resolve(found, code, tile, known):
    """L'état de chaque symbole : porté par la tuile, connu de Taxo sans que la tuile le porte, ou non résolu.

    `known` : `types` (noms simples des types du projet), `calls` (noms des méthodes que Taxo relie par CALLS) et `members`
    (noms des méthodes déclarées par la classe)."""
    own = declared_names(code)
    fields, types = field_names(tile.get('fields', ())), type_names(tile)
    out = []
    for (name, role), _ in found.items():
        if role in (FIELD, LOCAL) and name in own:
            out.append(Resolution(name, LOCAL, IN_TILE, 'déclaré dans la méthode'))
        elif role == FIELD and name in fields:
            out.append(Resolution(name, role, IN_TILE, 'déclaration du champ dans la tuile'))
        elif role == TYPE and name in types:
            out.append(Resolution(name, role, IN_TILE, 'en-tête du type dans la tuile'))
        elif role == TYPE and name in known['types']:
            out.append(Resolution(name, role, KNOWN_NOT_CARRIED, 'type du projet, en-tête absent de la tuile'))
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
    linked = carried + sum(item.state == KNOWN_NOT_CARRIED for item in resolutions)
    return (carried / total if total else 1.0), (linked / total if total else 1.0)


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


def report(exchange, paths, repository, analysis, seconds, options):
    classes = [name for name in options.classes.split(',') if name]
    wanted = [name for name in options.wanted.split(',') if name]
    methods = pick(methods_of(exchange, classes), options.limit, wanted)
    context = {'headers': {}, 'types': paths._project_types(exchange)}
    known_types = set(context['types'])
    rows, unresolved, refused, imports = [], Counter(), Counter(), Counter()
    commit = exchange.snapshot['commit']
    for method in methods:
        tile, reason, _, _ = paths._tile(exchange, 1, method, context, set())
        if tile is None:
            refused[reason] += 1
            continue
        owner = method.split('#', 1)[0]
        own_name = method.split('#', 1)[1].split('(')[0]
        calls = {fact['object'].split('#')[-1].split('(')[0] for fact in exchange.query(subject=method, relation='CALLS', kind='ASSERTION')}
        members = {fact['object'].split('#', 1)[1].split('(')[0] for fact in exchange.query(subject=owner, relation='CONTAINS', kind='ASSERTION')
                   if '#' in fact['object'] and '(' in fact['object']}
        found = symbols(tile['code'], own_name)
        resolutions = resolve(found, tile['code'], tile, {'types': known_types, 'calls': calls, 'members': members})
        strict, linked = coverage(resolutions)
        counts = Counter(item.state for item in resolutions)
        rows.append((paths._short(method), len(resolutions), counts[IN_TILE], counts[KNOWN_NOT_CARRIED], counts[UNRESOLVED], strict, linked,
                     len(tile['code'].encode()) + sum(len(text.encode()) for text in tile['fields'])
                     + len((tile.get('class') or {}).get('text', '').encode())))
        content, _ = exchange.sources.history.source(exchange.project_id, commit, tile['path'])
        text = content.decode('utf-8', 'replace') if content else ''
        for item in resolutions:
            if item.state == UNRESOLVED:
                unresolved[(item.name, item.role)] += 1
                imports[import_kind(item.name, text) if item.role == TYPE else 'membre ou appel'] += 1
    print(f'# Couverture des symboles des tuiles — {repository.name}\n')
    facts = sum(item['fact_count'] for item in analysis['evaluations'])
    print(f'Analyse complète : {seconds:.1f} s, {facts} faits, `{analysis["id"]}`. '
          f'{len(methods)} méthodes retenues, {len(rows)} tuiles construites, refusées : {dict(refused) or "aucune"}.\n')
    print('| Méthode | Symboles | Portés | Connus, non portés | Non résolus | Couverture stricte | Avec liens | Octets |')
    print('| --- | --- | --- | --- | --- | --- | --- | --- |')
    for name, total, carried, linked_count, missing, strict, linked, size in rows:
        print(f'| `{name}` | {total} | {carried} | {linked_count} | {missing} | {strict:.0%} | {linked:.0%} | {size} |')
    total = sum(row[1] for row in rows)
    print(f'\n**Ensemble** : {total} symboles ; couverture stricte {sum(r[2] for r in rows) / total:.0%}'
          f' ; avec les liens connus de Taxo {(sum(r[2] for r in rows) + sum(r[3] for r in rows)) / total:.0%}.\n' if total else '\nAucun symbole.\n')
    missing = sum(imports.values())
    print('**Ce que les imports expliqueraient** parmi les symboles non résolus '
          f'({missing}) : ' + ', '.join(f'{kind} {count}' for kind, count in imports.most_common()) + '.\n')
    print('| Nom non résolu | Rôle | Méthodes |')
    print('| --- | --- | --- |')
    for (name, role), count in unresolved.most_common(25):
        print(f'| `{name}` | {role} | {count} |')


if __name__ == '__main__':
    main()
