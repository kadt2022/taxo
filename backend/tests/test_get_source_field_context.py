"""`get_source` joint, dans une section distincte (`field_context`), la déclaration exacte des champs du type courant
que la méthode lue utilise comme receveurs d'appels (proposition « contexte des champs », version 1).

La pièce de la méthode reste exacte et inchangée. Un nom masqué par un paramètre ou une variable locale n'est pas un
champ ; les champs hérités, les autres usages et les lambdas ne sont pas suivis, et la réponse le dit. La vérité est
écrite à la main dans les sources ci-dessous.
"""
import json

import pytest

from app.facts import content_hash
from app.protocol.domain import source as policy
from test_get_source import assert_consistent, client_for, read

ROOT = 'src/main/java/com/acme/'
ORDERS = 'symbol:java:com.acme.Orders'
LINES = [
    'package com.acme;',
    '',
    'import java.util.List;',
    'import java.util.Set;',
    'import java.util.concurrent.ConcurrentHashMap;',
    '',
    'public class Orders extends Base {',
    '    /** Javadoc : jamais jointe. */',
    '    @Deprecated',
    '    private final Set<String> items =',
    '        ConcurrentHashMap.newKeySet();',
    '    private final StringBuilder log = new StringBuilder();',
    '    private int count;',
    '',
    '    public void add(String item) {',
    '        items.add(item);',
    '        this.log.append(item);',
    '        items.remove("");',
    '        count++;',
    '    }',
    '',
    '    public void shadowed(StringBuilder log) {',
    '        log.append("x");',
    '    }',
    '',
    '    public Set<String> all() {',
    '        return Set.copyOf(items);',
    '    }',
    '',
    '    public void inherited() {',
    '        names.clear();',
    '    }',
    '',
    '    public void later() {',
    '        Runnable task = () -> log.append("y");',
    '    }',
    '}',
    '',
    'class Base {',
    '    protected List<String> names;',
    '}',
    '']
SOURCE = '\n'.join(LINES)
ITEMS = '    @Deprecated\n    private final Set<String> items =\n        ConcurrentHashMap.newKeySet();'
LOG = '    private final StringBuilder log = new StringBuilder();'


def line(text):
    return LINES.index(text) + 1


@pytest.fixture(scope='module', name='java_repo')
def java_repo_fixture(tmp_path_factory):
    from conftest import run_git
    root = tmp_path_factory.mktemp('fields') / 'repo'
    root.mkdir()
    run_git(root, 'init', '-q')
    target = root / f'{ROOT}Orders.java'
    target.parent.mkdir(parents=True)
    target.write_text(SOURCE)
    run_git(root, 'add', '-A')
    run_git(root, 'commit', '-qm', 'initial')
    return root, run_git(root, 'rev-parse', 'HEAD')


@pytest.fixture(scope='module', name='taxo')
def taxo_fixture(java_repo, tmp_path_factory):
    client, url = client_for(java_repo[0], tmp_path_factory.mktemp('db'))
    with client:
        yield client, url


def context(response):
    return [(item['field'], item['text']) for item in response['field_context']]


def test_the_fields_used_as_receivers_are_joined_with_their_whole_declaration(taxo):
    response = read(*taxo, f'{ORDERS}#add(String)')
    assert response['outcome'] == 'OK'
    assert context(response) == [(f'{ORDERS}#items', ITEMS), (f'{ORDERS}#log', LOG)], 'ordre d’usage, sans doublon'
    items = response['field_context'][0]
    assert (items['line_start'], items['line_end']) == (line('    @Deprecated'), line('        ConcurrentHashMap.newKeySet();'))
    assert items['content_hash'] == content_hash(SOURCE.encode(), items['line_start'], items['line_end'])
    assert items['resolution'] == 'RESOLVED' and 'path' not in items
    assert response['path'] == f'{ROOT}Orders.java', 'les lignes d’un champ sont celles du fichier de la pièce'
    assert 'Javadoc' not in items['text']
    assert_consistent(response)


def test_the_piece_of_the_method_is_unchanged(taxo):
    piece, = read(*taxo, f'{ORDERS}#add(String)')['items']
    assert piece['text'].startswith('    public void add(String item) {') and 'Set<String>' not in piece['text']
    assert (piece['line_start'], piece['line_end']) == (line('    public void add(String item) {'), line('    public void add(String item) {') + 5)


def test_a_field_used_otherwise_than_as_a_receiver_is_not_joined(taxo):
    """`count++` dans `add`, `Set.copyOf(items)` dans `all` : non suivis en version 1."""
    assert f'{ORDERS}#count' not in dict(context(read(*taxo, f'{ORDERS}#add(String)')))
    assert context(read(*taxo, f'{ORDERS}#all()')) == []


def test_a_parameter_that_masks_a_field_is_not_a_field(taxo):
    assert context(read(*taxo, f'{ORDERS}#shadowed(StringBuilder)')) == []


def test_an_inherited_field_and_a_lambda_are_not_followed_and_the_scope_says_so(taxo):
    for method in ('inherited()', 'later()'):
        response = read(*taxo, f'{ORDERS}#{method}')
        assert context(response) == []
        assert response['field_context_scope'] == policy.FIELD_CONTEXT_SCOPE
        assert 'INHERITED_FIELDS' in response['field_context_scope']['not_followed']


def test_a_type_is_read_as_before_without_a_field_context(taxo):
    response = read(*taxo, ORDERS)
    assert 'field_context' not in response and 'field_context_scope' not in response
    assert response['items'][0]['text'].startswith('public class Orders')


def test_beyond_its_own_limit_the_rest_is_counted_never_silent(taxo, monkeypatch):
    first = len(json.dumps(read(*taxo, f'{ORDERS}#add(String)')['field_context'][0], ensure_ascii=False).encode())
    monkeypatch.setattr(policy, 'MAX_FIELD_CONTEXT_BYTES', first)
    response = read(*taxo, f'{ORDERS}#add(String)')
    assert context(response) == [(f'{ORDERS}#items', ITEMS)]
    assert {'what': 'field_context', 'count': 1, 'reason': 'FIELD_CONTEXT_LIMIT'} in response['not_sent']
    assert response['items'][0]['text'].startswith('    public void add'), 'la pièce passe toujours en premier'


def test_a_tight_operation_budget_keeps_the_piece_and_counts_the_context(taxo):
    client, url = taxo
    full = read(client, url, f'{ORDERS}#add(String)')
    body = {'requests': [{'operation': 'get_source', 'arguments': {'reference': f'{ORDERS}#add(String)'},
                          'max_bytes': full['bytes'] - 120}], 'consent': {'source': True}}
    tight = client.post(url, json=body).json()['responses'][0]
    assert tight['outcome'] == 'OK' and tight['items'] == full['items']
    assert len(tight['field_context']) < len(full['field_context'])
    assert any(item['what'] == 'field_context' for item in tight['not_sent'])


def test_without_consent_nothing_is_read_not_even_the_context(taxo):
    response = read(*taxo, f'{ORDERS}#add(String)', consent={'source': False})
    assert response['outcome'] == 'ERROR' and 'field_context' not in response


def test_a_working_tree_analysis_gives_neither_piece_nor_context(java_repo, tmp_path):
    client, url = client_for(java_repo[0], tmp_path, mode='working-tree')
    with client:
        response = read(client, url, f'{ORDERS}#add(String)')
    assert response['outcome'] == 'ERROR' and 'field_context' not in response


def test_a_secret_in_a_joined_declaration_is_masked_before_the_model_and_says_so(make_repo, tmp_path, monkeypatch):
    """Le contexte passe par la même protection que la pièce : la valeur ne sort pas, le masque reste visible."""
    import test_minia_source_reading as reading
    from test_minia_explore import answer, call, statement
    from test_minia_general import Scripted, analysis_of
    vault = '\n'.join(['package com.example.demo.service;', '', 'public class Vault {',
                       '    private final String password = "hunter2-in-field";', '',
                       '    public int size() {', '        return password.length();', '    }', '}', ''])
    monkeypatch.setattr(reading, 'FILES', {f'{reading.ROOT}service/Vault.java': vault})
    model = Scripted(
        lambda message: call('find_references', analysis=analysis_of(message), prefix='Vault.size', match='NAME'),
        call('get_source', reference='symbol:java:com.example.demo.service.Vault#size()'),
        answer(statement('interpretation', 'Rien à conclure.')))
    reading.ask(make_repo, tmp_path, model, question='Que fait Vault.size() ?')
    piece = json.loads(model.calls[2][1])['trajectory'][-1]['response']
    joined, = piece['field_context']
    assert joined['field'] == 'symbol:java:com.example.demo.service.Vault#password'
    assert joined['text'] == '    private final String password = "******";'
    assert 'hunter2-in-field' not in json.dumps(model.calls)
