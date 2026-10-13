"""`get_source` d'une méthode dit où elle mène (`uses`) : les références que la Maille établit déjà — les méthodes
qu'elle appelle (`CALLS`) et le type des champs qu'elle utilise (`TYPED_AS`) —, sans leur code. Un modèle n'a plus à
deviner une référence à partir d'un nom lu dans le code : il la reçoit de Taxo, et peut la lire à son tour."""
import pytest

from app.minia.application import sources
from app.protocol.domain import source as policy
from test_get_source import client_for, read

ROOT = 'src/main/java/com/acme/'
SERVICE, REPOSITORY = 'symbol:java:com.acme.Enrolments', 'symbol:java:com.acme.Store'
ENROL, SAVE = f'{SERVICE}#enrol(Long)', f'{REPOSITORY}#save(Long)'
FILES = {
    f'{ROOT}Store.java': '\n'.join([
        'package com.acme;',
        '',
        'import java.util.HashSet;',
        'import java.util.Set;',
        '',
        'public class Store {',
        '    private final Set<Long> ids = new HashSet<>();',
        '',
        '    public boolean save(Long id) {',
        '        return ids.add(id);',
        '    }',
        '}',
        '']),
    f'{ROOT}Enrolments.java': '\n'.join([
        'package com.acme;',
        '',
        'public class Enrolments {',
        '    private final Store store;',
        '',
        '    public Enrolments(Store store) {',
        '        this.store = store;',
        '    }',
        '',
        '    public boolean enrol(Long id) {',
        '        check(id);',
        '        return store.save(id);',
        '    }',
        '',
        '    private void check(Long id) {',
        '    }',
        '}',
        '']),
}


@pytest.fixture(scope='module', name='taxo')
def taxo_fixture(tmp_path_factory):
    from conftest import run_git
    root = tmp_path_factory.mktemp('uses') / 'repo'
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


def test_a_method_says_the_methods_it_calls_and_the_types_of_its_fields(taxo):
    response = read(*taxo, ENROL)
    assert response['outcome'] == 'OK'
    assert {'relation': 'CALLS', 'reference': SAVE} in response['uses']
    assert {'relation': 'CALLS', 'reference': f'{SERVICE}#check(Long)'} in response['uses']
    assert {'relation': 'TYPED_AS', 'from': f'{SERVICE}#store', 'reference': REPOSITORY} in response['uses']
    assert response['uses_scope'] == policy.USES_SCOPE
    assert all('text' not in item for item in response['uses']), 'des références, jamais du code'


def test_the_piece_is_unchanged(taxo):
    piece, = read(*taxo, ENROL)['items']
    assert 'return store.save(id);' in piece['text'] and 'class Store' not in piece['text']


def test_a_call_outside_the_sources_is_not_a_use(taxo):
    """`ids.add(id)` vise le JDK : aucun fait `CALLS`, donc rien dans `uses` ; la portée le dit."""
    response = read(*taxo, SAVE)
    assert response['uses'] == []
    assert 'TYPES_OUTSIDE_THE_SOURCES' in response['uses_scope']['not_followed']


def test_a_type_is_read_as_before(taxo):
    response = read(*taxo, SERVICE)
    assert 'uses' not in response and 'uses_scope' not in response


def test_beyond_the_limit_the_rest_is_counted(taxo, monkeypatch):
    monkeypatch.setattr(policy, 'MAX_USES', 1)
    response = read(*taxo, ENROL)
    assert len(response['uses']) == 1
    assert {'what': 'uses', 'count': 2, 'reason': 'LIMIT'} in response['not_sent']


def test_every_use_beyond_the_operation_budget_is_counted(taxo):
    client, url = taxo
    full = read(client, url, ENROL)
    body = {'requests': [{'operation': 'get_source', 'arguments': {'reference': ENROL},
                          'max_bytes': full['bytes'] - 60}], 'consent': {'source': True}}
    tight = client.post(url, json=body).json()['responses'][0]
    counted = sum(item['count'] for item in tight['not_sent'] if item['what'] == 'uses')
    assert len(tight['uses']) + counted == len(full['uses']), 'ce qui ne tient pas est compté, un par un'


def test_minia_receives_the_uses_as_references(taxo):
    """Une référence de `uses` est « reçue de Taxo » : Minia peut la lire, et la garde peut la proposer."""
    response = read(*taxo, ENROL)
    exchanged = [{'operation': 'get_source', 'arguments': {'reference': ENROL}, 'response': response}]
    assert sources.received(SAVE, exchanged)
    assert sources.received(REPOSITORY, exchanged)
