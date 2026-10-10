"""Classification d'une Tuile MIP et restrictions de divulgation (récit TAXO-MIP-ADT-01 § 21 bis).

La classification décrit une Tuile déjà construite. Elle n'en fait pas partie et ne change ni sa sélection ni ses
faits. Elle est calculée sur ce que la Tuile transporte réellement, après coupe par les budgets : une catégorie
n'est annoncée que si un contenu de cette catégorie est présent. Elle ne lit rien d'autre que la Tuile et ne dit rien
de ce que le code fait.

- `nature` : le type de la référence centrale, lu dans sa syntaxe. Un symbole appelable (`…#nom(…)`) est une méthode,
  un symbole sans membre un type, tout autre symbole un membre. La Maille ne dit pas si un type est une classe, une
  interface, un record ou une énumération : la nature reste `TYPE`.
- `language` : celui que la référence centrale écrit (`symbol:java:…`), sinon celui d'un fait `WRITTEN_IN` de la
  Tuile, sinon `null`. Jamais deviné.
- `content` : les catégories présentes, dans un ordre fixe.
- `provenance` : l'instantané de la Tuile, la révision des faits et les producteurs des faits transmis.

Les restrictions de divulgation sont rendues à part, dans `disclosure` : elles disent quelles protections s'appliquent
au contenu présent avant toute transmission à un fournisseur de modèle (ARCHITECTURE § 12.6), pas ce qu'il est.
"""
CLASSIFICATION_VERSION = 'tile-classification/1'
DISCLOSURE_VERSION = 'tile-disclosure/1'

FACTS, RELATIONS, EVIDENCE = 'FACTS', 'RELATIONS', 'EVIDENCE'
CODE_SOURCE, COMMIT_METADATA, COVERAGE, FRONTIER = 'CODE_SOURCE', 'COMMIT_METADATA', 'COVERAGE', 'FRONTIER'
# L'ordre de présentation des catégories ; `CODE_SOURCE` n'est jamais annoncée par une Tuile de faits : une pièce
# source est consultée à part, sous son propre consentement (`get_source` de `taxo-query/1`, classée à part).
CATEGORIES = (FACTS, RELATIONS, EVIDENCE, CODE_SOURCE, COMMIT_METADATA, COVERAGE, FRONTIER)

PERSON_IDENTITY, COMMIT_MESSAGE = 'PERSON_IDENTITY', 'COMMIT_MESSAGE'
_SYMBOL, _MEMBER, _CALLABLE_END = 'symbol', '#', ')'
_COMMIT_RELATIONS = frozenset({'HAS_COMMIT', 'CHILD_OF', 'AUTHORED_BY', 'CHANGES'})
# Les qualificatifs Git d'un commit, tels que l'évaluateur Git les écrit sur `HAS_COMMIT`.
_COMMIT_FIELDS = ('authored_at', 'committed_at', 'message')


def _type(reference):
    return reference.split(':', 1)[0]


def nature(reference):
    """La nature lue dans la syntaxe de la référence ; aucun fait n'est consulté."""
    kind = _type(reference)
    if kind != _SYMBOL:
        return kind.upper().replace('-', '_')
    if _MEMBER not in reference:
        return 'TYPE'
    return 'METHOD' if reference.endswith(_CALLABLE_END) and '(' in reference.rsplit(_MEMBER, 1)[1] else 'MEMBER'


def _language(reference, facts):
    if _type(reference) == _SYMBOL:
        parts = reference.split(':', 2)
        if len(parts) == 3 and parts[1]:
            return parts[1]
    for item in facts:
        fact = item['fact']
        if fact['subject'] == reference and fact['relation'] == 'WRITTEN_IN':
            return fact['object'].split(':', 1)[1]
    return None


def _commit_metadata(facts):
    """Les champs Git effectivement transmis : le SHA de chaque commit d'un fait Git, ses qualificatifs présents, et
    l'auteur seulement si un fait `AUTHORED_BY` est dans la Tuile."""
    commits, fields = set(), set()
    for item in facts:
        fact = item['fact']
        if fact['relation'] not in _COMMIT_RELATIONS:
            continue
        commits.update(value for value in (fact['subject'], fact.get('object')) if _type(str(value)) == 'commit')
        fields.update(name for name in _COMMIT_FIELDS if name in fact.get('qualifiers', {}))
        if fact['relation'] == 'AUTHORED_BY':
            fields.add('author')
    if not commits:
        return None
    return {'commits': len(commits), 'fields': ['sha', *sorted(fields)]}


def _far_end(item):
    """L'extrémité atteinte par un fait : son objet en sortant, son sujet en entrant. Une valeur littérale (une
    expression d'autorisation écrite) n'est jamais un nœud de la Tuile."""
    fact = item['fact']
    return fact['subject'] if item['via']['direction'] == 'INCOMING' else fact.get('object')


def _content(tile, commits):
    facts, nodes = tile['facts'], {node['reference'] for node in tile['nodes']}
    present = {
        FACTS: bool(facts),
        RELATIONS: any(_far_end(item) in nodes for item in facts),
        EVIDENCE: any(item.get('evidence') for item in facts),
        CODE_SOURCE: False,
        COMMIT_METADATA: commits is not None,
        COVERAGE: bool(tile['coverage']),
        FRONTIER: bool(tile['frontier']),
    }
    return [category for category in CATEGORIES if present[category]]


def _producers(facts):
    seen = {(item['fact']['produced_by']['producer_id'], item['fact']['produced_by']['producer_version'])
            for item in facts if item['fact'].get('produced_by')}
    return [{'id': identifier, 'version': version} for identifier, version in sorted(seen)]


def classify(tile, profile=None):
    """La classification d'une Tuile `OK`, calculée sur son contenu transmis."""
    reference, facts = tile['root']['reference'], tile['facts']
    commits = _commit_metadata(facts)
    classification = {
        'version': CLASSIFICATION_VERSION,
        'nature': nature(reference),
        'language': _language(reference, facts),
        'profile': profile.identifier if profile is not None else None,
        'content': _content(tile, commits),
        'provenance': {'snapshot': tile['snapshot'], 'facts_revision': tile['wire']['facts_revision'],
                       'producers': _producers(facts)},
    }
    if commits is not None:
        classification['commit_metadata'] = commits
    return classification


def disclosure(tile):
    """Les protections qui s'appliquent au contenu présent avant tout fournisseur de modèle, séparées de la
    classification. Une identité de personne est remplacée par un pseudonyme ; un message de commit perd ses trailers
    et ses identités (ARCHITECTURE § 12.6, point 8)."""
    restrictions = []
    references = {value for item in tile['facts'] for value in (item['fact']['subject'], item['fact'].get('object'))}
    references.update(node['reference'] for node in tile['nodes'])
    if any(isinstance(value, str) and _type(value) == 'person' for value in references):
        restrictions.append({'code': PERSON_IDENTITY, 'for_model': 'PSEUDONYMIZED'})
    if any('message' in item['fact'].get('qualifiers', {}) for item in tile['facts']):
        restrictions.append({'code': COMMIT_MESSAGE, 'for_model': 'TRAILERS_REMOVED_IDENTITIES_PSEUDONYMIZED'})
    return {'version': DISCLOSURE_VERSION, 'restrictions': restrictions}
