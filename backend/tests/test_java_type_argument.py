"""`TYPE_ARGUMENT` : un argument de type écrit d'un champ, quand il est un type des sources. `Set<Enrollment>
enrollments` donne `…#enrollments TYPE_ARGUMENT …Enrollment` ; le conteneur (`Set`, hors des sources) n'est jamais
interprété. Un joker, une variable de type ou un type hors des sources ne donnent rien : moins de faits, mais vrais.
La lecture d'une méthode qui utilise le champ y mène (`uses`)."""
import pytest

from test_get_source import client_for, exchange, read

ROOT = 'src/main/java/com/acme/'
STORE, ITEM = 'symbol:java:com.acme.Store', 'symbol:java:com.acme.Item'
FILES = {
    f'{ROOT}Item.java': 'package com.acme;\n\npublic record Item(Long id) {\n}\n',
    f'{ROOT}Shelf.java': 'package com.acme;\n\nimport java.util.List;\n\npublic record Shelf(List<Item> items) {\n}\n',
    f'{ROOT}Tagged.java': '\n'.join(['package com.acme;', '', 'import java.util.List;', '',
                                     'public class Tagged {', '    private List<@Nullable Item> maybe;', '}', '']),
    f'{ROOT}Nullable.java': 'package com.acme;\n\npublic @interface Nullable {\n}\n',
    f'{ROOT}Store.java': '\n'.join([
        'package com.acme;',
        '',
        'import java.util.List;',
        'import java.util.Map;',
        'import java.util.Set;',
        '',
        'public class Store<T> {',
        '    private final Set<Item> items = new java.util.HashSet<>();',
        '    private Map<String, Item> byName;',
        '    private List<? extends Item> wild;',
        '    private Set<String> names;',
        '    private List<T> values;',
        '    private Item single;',
        '',
        '    public boolean add(Item item) {',
        '        return items.add(item);',
        '    }',
        '}',
        '']),
}


@pytest.fixture(scope='module', name='taxo')
def taxo_fixture(tmp_path_factory):
    from conftest import run_git
    root = tmp_path_factory.mktemp('arguments') / 'repo'
    root.mkdir()
    run_git(root, 'init', '-q')
    for path, content in FILES.items():
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
    run_git(root, 'add', '-A')
    run_git(root, 'commit', '-qm', 'initial')
    client, url = client_for(root, tmp_path_factory.mktemp('db'))
    with client:
        yield client, url


def arguments(taxo, owner=STORE):
    client, url = taxo
    found = exchange(client, url, ('find_facts', {'relation': 'TYPE_ARGUMENT'}))['responses'][0]
    return sorted((item['fact']['subject'].split('#')[1], item['fact']['object']) for item in found['items']
                  if item['fact']['subject'].split('#')[0] == owner)


def test_a_source_type_argument_is_a_fact(taxo):
    assert ('items', ITEM) in arguments(taxo)
    assert ('byName', ITEM) in arguments(taxo), 'Map<String, Item> : seul le type des sources'


def test_a_wildcard_a_type_variable_or_an_outside_type_gives_nothing(taxo):
    named = {field for field, _ in arguments(taxo)}
    assert named == {'items', 'byName'}, 'ni joker, ni variable de type, ni String, ni champ non générique'


def test_the_container_is_never_interpreted(taxo):
    client, url = taxo
    typed = exchange(client, url, ('find_facts', {'subject': f'{STORE}#items', 'relation': 'TYPED_AS'}))['responses'][0]
    assert typed['items'] == [], 'Set est hors des sources : aucun type déclaré inventé'


def test_reading_a_method_leads_to_the_element_type(taxo):
    response = read(*taxo, f'{STORE}#add({ITEM.split(".")[-1]})')
    assert {'relation': 'TYPE_ARGUMENT', 'from': f'{STORE}#items', 'reference': ITEM} in response['uses']


def test_describe_announces_the_relation(taxo):
    client, url = taxo
    described = exchange(client, url, ('describe', {}))['responses'][0]
    relations = {item['relation'] for item in described['items'] if item['kind'] == 'relation'}
    assert 'TYPE_ARGUMENT' in relations


def test_a_record_component_gives_its_type_argument(taxo):
    assert arguments(taxo, 'symbol:java:com.acme.Shelf') == [('items', ITEM)]


def test_a_type_use_annotation_does_not_hide_the_argument(taxo):
    assert arguments(taxo, 'symbol:java:com.acme.Tagged') == [('maybe', ITEM)]
