"""`get_source` : le code d'un symbole déclaré, sous son propre double consentement (TAXO-MIP-ADT-01, PR B).

La vérité est écrite à la main dans les sources ci-dessous : `get(Long)` et `get(String)` sont deux surcharges,
`twice(int)` une signature ambiguë, `@Toto` une annotation inconnue de toute bibliothèque.
"""
import pytest
from fastapi.testclient import TestClient

from app.bootstrap import settings
from app.bootstrap.database import Base
from app.facts import content_hash
from app.main import create_app
from app.protocol.domain import source as policy

ROOT = 'src/main/java/com/acme/'
SERVICE = 'symbol:java:com.acme.StudentService'
GET_LONG, GET_STRING = f'{SERVICE}#get(Long)', f'{SERVICE}#get(String)'
SERVICE_SOURCE = '\n'.join([
    'package com.acme;',
    '',
    'import org.springframework.stereotype.Component;',
    '',
    '/** Javadoc : jamais lue avec la déclaration. */',
    '@Component',
    'public class StudentService {',
    '    private final String prefix = "s-";',
    '',
    '    @Toto(role = "ADMIN")',
    '    public String get(Long id) {',
    '        return prefix + id;',
    '    }',
    '',
    '    public String get(String name) {',
    '        return name.trim();',
    '    }',
    '',
    '    public void twice(int a) { }',
    '    public void twice(int b) { }',
    '}',
    ''])
SOURCES = {
    f'{ROOT}StudentService.java': SERVICE_SOURCE,
    f'{ROOT}Toto.java': 'package com.acme;\n\npublic @interface Toto {\n    String role();\n}\n',
    '.env': 'SECRET=1\n',
}


def client_for(repo, tmp_path, reading='symbol', source_context='off', mode='commit'):
    tmp_path.mkdir(parents=True, exist_ok=True)
    app = create_app(f'sqlite:///{tmp_path / "source.db"}', [repo], minia={}, source_context=source_context,
                     source_reading=reading)
    Base.metadata.create_all(app.state.engine)
    client = TestClient(app)
    project = client.post('/api/projects', json={'name': 'Sources', 'path': str(repo)}).json()
    client.post(f'/api/projects/{project["id"]}/scans', params={'mode': mode})
    return client, f'/api/projects/{project["id"]}/taxo-query'


def exchange(client, url, *requests, **options):
    body = {'requests': [{'operation': name, 'arguments': arguments} for name, arguments in requests], **options}
    response = client.post(url, json=body)
    assert response.status_code == 200, response.text
    return response.json()


def read(client, url, reference, consent=None, **options):
    consent = {'source': True} if consent is None else consent
    return exchange(client, url, ('get_source', {'reference': reference}), consent=consent, **options)['responses'][0]


def assert_consistent(response):
    """A6 : la classification annonce `CODE_SOURCE` si et seulement si du code est transmis ; un refus n'en a pas."""
    if response['outcome'] == 'ERROR':
        assert 'classification' not in response and 'disclosure' not in response
        return
    sent = [item for item in response['items'] if item.get('text')]
    assert response['classification']['content'] == (['CODE_SOURCE'] if sent else [])
    assert bool(response['disclosure']['restrictions']) == bool(sent)
    assert not any('fact' in item or 'ref' in item for item in response['items']), 'jamais un fait'


@pytest.fixture(scope='module', name='java_repo')
def java_repo_fixture(tmp_path_factory):
    from conftest import run_git
    root = tmp_path_factory.mktemp('java') / 'repo'
    root.mkdir()
    run_git(root, 'init', '-q')
    for path, content in SOURCES.items():
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
    run_git(root, 'add', '-A')
    run_git(root, 'commit', '-qm', 'initial')
    return root, run_git(root, 'rev-parse', 'HEAD')


@pytest.fixture(scope='module', name='taxo')
def taxo_fixture(java_repo, tmp_path_factory):
    client, url = client_for(java_repo[0], tmp_path_factory.mktemp('db'))
    with client:
        yield client, url, java_repo[1]


def test_an_overload_is_read_alone_with_its_annotations_and_lines(taxo):
    """B1 : `get(Long)` rend cette méthode, ses annotations et ses lignes, jamais l'autre surcharge."""
    client, url, commit = taxo
    response = read(client, url, GET_LONG)
    assert response['outcome'] == 'OK' and response['commit'] == commit and response['not_sent'] == []
    piece, = response['items']
    assert piece['text'] == '    @Toto(role = "ADMIN")\n    public String get(Long id) {\n        return prefix + id;\n    }'
    assert (piece['path'], piece['line_start'], piece['line_end'], piece['truncated']) == (
        f'{ROOT}StudentService.java', 10, 13, False)
    assert piece['content_hash'] == content_hash(SERVICE_SOURCE.encode(), 10, 13)
    other = read(client, url, GET_STRING)['items'][0]
    assert 'trim' in other['text'] and 'Long' not in other['text']
    assert_consistent(response)


def test_the_type_is_read_with_its_written_annotation_and_without_its_javadoc(taxo):
    """B2 et B3 : la déclaration de la classe restitue `@Component` tel qu'écrit ; la Javadoc n'en fait pas partie."""
    client, url, _ = taxo
    response = read(client, url, SERVICE)
    piece, = response['items']
    assert piece['text'].startswith('@Component\npublic class StudentService {') and piece['text'].endswith('}')
    assert 'Javadoc' not in piece['text'] and '@Service' not in piece['text']
    assert response['classification'] == {
        'version': 'source-classification/1', 'nature': 'TYPE', 'language': 'java', 'content': ['CODE_SOURCE'],
        'provenance': {'snapshot': response['snapshot'], 'path': f'{ROOT}StudentService.java',
                       'producer': 'taxo.java-calls'}}
    assert [item['code'] for item in response['disclosure']['restrictions']] == [
        'CODE_SOURCE', 'SECRETS', 'PERSON_IDENTITY']
    assert_consistent(response)


def test_the_code_is_the_one_of_the_analysis_commit(java_repo, tmp_path):
    """B4 : un commit plus récent, non analysé, ne change pas le code rendu."""
    from conftest import run_git
    root, first = java_repo
    copy = tmp_path / 'later'
    run_git(tmp_path, 'clone', '-q', str(root), str(copy))
    client, url = client_for(copy, tmp_path / 'db')
    path = copy / f'{ROOT}StudentService.java'
    path.write_text(SERVICE_SOURCE.replace('prefix + id', 'prefix + id + "!"'))
    run_git(copy, 'commit', '-qam', 'plus tard')
    with client:
        response = read(client, url, GET_LONG)
    assert response['commit'] == first and 'return prefix + id;' in response['items'][0]['text']


def test_a_working_tree_analysis_whose_lines_differ_from_the_commit_sends_nothing(java_repo, tmp_path):
    """Les lignes de la preuve n'ont plus la même empreinte au commit : rien n'est transmis, et la raison est dite."""
    from conftest import run_git
    root, _ = java_repo
    copy = tmp_path / 'dirty'
    run_git(tmp_path, 'clone', '-q', str(root), str(copy))
    (copy / f'{ROOT}StudentService.java').write_text(SERVICE_SOURCE.replace('public String get(Long id)',
                                                                            'public String get(Long key)'))
    client, url = client_for(copy, tmp_path / 'db', mode='working-tree')
    with client:
        response = read(client, url, GET_LONG)
    assert response['outcome'] == 'OK' and response['items'] == []
    assert response['not_sent'] == [{'what': 'source', 'reason': 'CHANGED'}]
    assert_consistent(response)


def test_without_the_exchange_consent_nothing_is_read_or_offered(taxo):
    """B5 : sans l'accord de l'échange, refus sans aucun code ; `describe` ne la propose pas."""
    client, url, _ = taxo
    refused = read(client, url, GET_LONG, consent={})
    assert refused['error']['code'] == 'NO_CONSENT' and 'prefix' not in str(refused)
    described = exchange(client, url, ('describe', {}))['responses'][0]
    assert 'get_source' not in [item.get('operation') for item in described['items']]
    assert described['consent'] == {'diff': False, 'source': False}
    consented = exchange(client, url, ('describe', {}), consent={'source': True})['responses'][0]
    assert 'get_source' in [item.get('operation') for item in consented['items']]
    assert_consistent(refused)


def test_the_server_setting_is_off_by_default_and_the_diff_never_authorizes_the_code(java_repo, tmp_path,
                                                                                     monkeypatch):
    """B5 et C3 : réglage serveur éteint par défaut ; le réglage et l'accord du diff n'autorisent jamais le code."""
    monkeypatch.delenv('TAXO_SOURCE_READING', raising=False)
    assert settings.taxo_source_reading() == 'off'
    client, url = client_for(java_repo[0], tmp_path / 'off', reading=None, source_context='diff')
    with client:
        for consent in ({'source': True}, {'diff': True}, {'diff': True, 'source': True}):
            refused = read(client, url, GET_LONG, consent=consent)
            assert refused['error']['code'] == 'NO_CONSENT' and 'prefix' not in str(refused)
        described = exchange(client, url, ('describe', {}), consent={'diff': True})['responses'][0]
        assert described['consent'] == {'diff': True}, 'describe reste celui d’avant'
    client, url = client_for(java_repo[0], tmp_path / 'on', source_context='diff')
    with client:
        assert read(client, url, GET_LONG, consent={'diff': True})['error']['code'] == 'NO_CONSENT'


def test_an_unknown_server_setting_is_refused_at_start(java_repo, tmp_path):
    with pytest.raises(ValueError):
        client_for(java_repo[0], tmp_path, reading='file')


@pytest.mark.parametrize('arguments', [
    {'reference': f'file:{ROOT}StudentService.java'},
    {'reference': f'{SERVICE}#prefix'},
    {'reference': GET_LONG, 'path': f'{ROOT}StudentService.java'},
    {'path': '.env'},
    {'reference': 'pas une référence'},
])
def test_a_file_a_field_or_a_path_is_refused_by_the_targeted_contract(taxo, arguments):
    """B6 : jamais un fichier entier ni un chemin libre ; un champ n'a pas de code propre."""
    client, url, _ = taxo
    refused = exchange(client, url, ('get_source', arguments), consent={'source': True})['responses'][0]
    assert refused['error']['code'] == 'INVALID_ARGUMENT' and 'SECRET' not in str(refused)


@pytest.mark.parametrize('reference', [f'{SERVICE}#twice(int)', f'{SERVICE}#absent()', 'symbol:java:com.acme.Nope'])
def test_an_ambiguous_or_unknown_symbol_is_refused(taxo, reference):
    client, url, _ = taxo
    refused = read(client, url, reference)
    assert refused['error']['code'] == 'NOT_AVAILABLE'
    assert_consistent(refused)


def test_a_long_declaration_is_truncated_on_a_whole_line_and_says_so(taxo, monkeypatch):
    """A6 : une pièce tronquée annonce toujours `CODE_SOURCE`, sa fin déclarée et l'empreinte de ce qui est transmis."""
    client, url, _ = taxo
    monkeypatch.setattr(policy, 'MAX_SOURCE_LINES', 3)
    response = read(client, url, SERVICE)
    piece, = response['items']
    assert piece['truncated'] and (piece['line_start'], piece['line_end']) == (6, 8)
    assert piece['declared'] == {'line_start': 6, 'line_end': 21}
    assert piece['text'].count('\n') == 2
    assert piece['content_hash'] == content_hash(SERVICE_SOURCE.encode(), 6, 8)
    assert_consistent(response)


def test_a_piece_larger_than_the_operation_budget_is_refused_without_a_false_classification(taxo):
    client, url, _ = taxo
    body = {'requests': [{'operation': 'get_source', 'arguments': {'reference': SERVICE}, 'max_bytes': 1500}],
            'consent': {'source': True}}
    refused = client.post(url, json=body).json()['responses'][0]
    assert refused['error']['code'] == 'BUDGET_EXHAUSTED'
    assert_consistent(refused)
